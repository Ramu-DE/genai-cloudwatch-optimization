"""
Metrics Collection for Wealth Management Agent Optimization

Compares fault-injected execution against baseline, calculates deltas,
generates root-cause analysis, and emits structured CloudWatch metrics.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

from fault_injectors import PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Result of comparing fault injection vs baseline execution"""
    scenario_id: int
    scenario_name: str
    fault_metrics: PerformanceMetrics
    baseline_metrics: PerformanceMetrics

    latency_delta_ms: float = 0.0
    latency_delta_percent: float = 0.0
    token_delta: int = 0
    token_delta_percent: float = 0.0
    cost_delta_usd: float = 0.0
    cost_delta_percent: float = 0.0
    tool_call_delta: int = 0

    root_cause: str = ""
    impact_summary: str = ""
    recommendation: str = ""

    def __post_init__(self):
        self._calculate_deltas()
        self._generate_root_cause_analysis()

    # ------------------------------------------------------------------
    def _calculate_deltas(self):
        self.latency_delta_ms = self.fault_metrics.latency_ms - self.baseline_metrics.latency_ms
        if self.baseline_metrics.latency_ms > 0:
            self.latency_delta_percent = (self.latency_delta_ms / self.baseline_metrics.latency_ms) * 100

        self.token_delta = self.fault_metrics.total_tokens - self.baseline_metrics.total_tokens
        if self.baseline_metrics.total_tokens > 0:
            self.token_delta_percent = (self.token_delta / self.baseline_metrics.total_tokens) * 100

        self.cost_delta_usd = self.fault_metrics.estimated_cost_usd - self.baseline_metrics.estimated_cost_usd
        if self.baseline_metrics.estimated_cost_usd > 0:
            self.cost_delta_percent = (self.cost_delta_usd / self.baseline_metrics.estimated_cost_usd) * 100

        self.tool_call_delta = self.fault_metrics.tool_calls - self.baseline_metrics.tool_calls

    # ------------------------------------------------------------------
    def _generate_root_cause_analysis(self):
        causes: List[str] = []

        if self.fault_metrics.injected_latency_ms > 0:
            causes.append(f"Injected latency: +{self.fault_metrics.injected_latency_ms:.0f}ms (DynamoDB / API delay)")

        if self.fault_metrics.bloat_tokens > 0:
            causes.append(f"Context bloat: +{self.fault_metrics.bloat_tokens} tokens (raw data in prompt)")

        if self.tool_call_delta > 0:
            causes.append(f"Redundant tool calls: +{self.tool_call_delta} extra round-trips")
        elif self.tool_call_delta < 0:
            causes.append(f"Reduced tool calls: {self.tool_call_delta} (optimized orchestration)")

        if self.fault_metrics.error_count > 0:
            causes.append(f"Tool errors: {self.fault_metrics.error_count} (required recovery)")

        if self.fault_metrics.retry_count > 0:
            causes.append(f"Retries: {self.fault_metrics.retry_count} (added latency)")

        self.root_cause = " | ".join(causes) if causes else "No significant fault detected"
        self.impact_summary = self._build_impact_summary()
        self.recommendation = self._build_recommendation()

    # ------------------------------------------------------------------
    def _build_impact_summary(self) -> str:
        parts: List[str] = []
        if abs(self.latency_delta_percent) > 10:
            direction = "slower" if self.latency_delta_ms > 0 else "faster"
            parts.append(f"{abs(self.latency_delta_percent):.0f}% {direction}")
        if abs(self.cost_delta_percent) > 10:
            direction = "more expensive" if self.cost_delta_usd > 0 else "cheaper"
            parts.append(f"{abs(self.cost_delta_percent):.0f}% {direction}")
        if abs(self.token_delta_percent) > 10:
            direction = "more tokens" if self.token_delta > 0 else "fewer tokens"
            parts.append(f"{abs(self.token_delta_percent):.0f}% {direction}")
        return ", ".join(parts) if parts else "Minimal performance impact"

    # ------------------------------------------------------------------
    def _build_recommendation(self) -> str:
        if self.fault_metrics.bloat_tokens > 3000:
            return "Summarize context before injection — use AgentCore Memory summaries instead of raw data"
        if self.tool_call_delta > 1:
            return "Bundle tool calls — combine portfolio, risk, and allocation into a single tool"
        if self.fault_metrics.injected_latency_ms > 1000:
            return "Add DynamoDB DAX cache or implement local caching for portfolio data"
        if self.fault_metrics.error_count > 0:
            return "Add circuit-breaker pattern for external market data APIs"
        if self.fault_metrics.retry_count > 0:
            return "Implement exponential backoff with jitter for transient failures"
        return "Performance is within acceptable range for financial advisory SLAs"

    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            'scenario_id': self.scenario_id,
            'scenario_name': self.scenario_name,
            'fault_metrics': self.fault_metrics.to_dict(),
            'baseline_metrics': self.baseline_metrics.to_dict(),
            'deltas': {
                'latency_ms': round(self.latency_delta_ms, 2),
                'latency_percent': round(self.latency_delta_percent, 1),
                'tokens': self.token_delta,
                'tokens_percent': round(self.token_delta_percent, 1),
                'cost_usd': round(self.cost_delta_usd, 6),
                'cost_percent': round(self.cost_delta_percent, 1),
                'tool_calls': self.tool_call_delta,
            },
            'analysis': {
                'root_cause': self.root_cause,
                'impact_summary': self.impact_summary,
                'recommendation': self.recommendation,
            },
        }


# ======================================================================
# Structured log emitter (EMF-compatible)
# ======================================================================

def emit_scenario_metrics_log(result: ComparisonResult):
    """Emit an EMF-compatible structured log line for CloudWatch Insights."""
    emf = {
        '_aws': {
            'Timestamp': int(datetime.utcnow().timestamp() * 1000),
            'CloudWatchMetrics': [{
                'Namespace': 'WealthMgmt/Optimization',
                'Dimensions': [['ScenarioId', 'ScenarioName']],
                'Metrics': [
                    {'Name': 'FaultLatencyMs', 'Unit': 'Milliseconds'},
                    {'Name': 'BaselineLatencyMs', 'Unit': 'Milliseconds'},
                    {'Name': 'LatencyDeltaPercent', 'Unit': 'Percent'},
                    {'Name': 'FaultTokens', 'Unit': 'Count'},
                    {'Name': 'BaselineTokens', 'Unit': 'Count'},
                    {'Name': 'FaultCostUsd', 'Unit': 'None'},
                    {'Name': 'BaselineCostUsd', 'Unit': 'None'},
                ]
            }]
        },
        'ScenarioId': str(result.scenario_id),
        'ScenarioName': result.scenario_name,
        'FaultLatencyMs': result.fault_metrics.latency_ms,
        'BaselineLatencyMs': result.baseline_metrics.latency_ms,
        'LatencyDeltaPercent': result.latency_delta_percent,
        'FaultTokens': result.fault_metrics.total_tokens,
        'BaselineTokens': result.baseline_metrics.total_tokens,
        'FaultCostUsd': result.fault_metrics.estimated_cost_usd,
        'BaselineCostUsd': result.baseline_metrics.estimated_cost_usd,
        'RootCause': result.root_cause,
        'Recommendation': result.recommendation,
    }
    print(json.dumps(emf))


# ======================================================================
# Batch comparison
# ======================================================================

def compare_all_scenarios(results: List[ComparisonResult]) -> Dict[str, Any]:
    """Aggregate a batch of comparison results into a summary report."""
    if not results:
        return {'status': 'empty', 'scenarios_tested': 0}

    total_cost_saved = sum(r.cost_delta_usd for r in results if r.cost_delta_usd < 0)
    worst_latency = max(results, key=lambda r: r.latency_delta_percent)
    worst_cost = max(results, key=lambda r: r.cost_delta_percent)

    return {
        'scenarios_tested': len(results),
        'total_potential_savings_usd': round(abs(total_cost_saved), 6),
        'worst_latency_scenario': {
            'id': worst_latency.scenario_id,
            'name': worst_latency.scenario_name,
            'delta_percent': round(worst_latency.latency_delta_percent, 1),
        },
        'worst_cost_scenario': {
            'id': worst_cost.scenario_id,
            'name': worst_cost.scenario_name,
            'delta_percent': round(worst_cost.cost_delta_percent, 1),
        },
        'recommendations': list({r.recommendation for r in results if r.recommendation}),
        'details': [r.to_dict() for r in results],
    }
