"""
Metrics Collection using AgentCore Observability

This module leverages AgentCore's built-in observability features including:
- Automatic CloudWatch metrics emission
- Automatic X-Ray tracing for tool calls
- Structured logging to CloudWatch Logs
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

from fault_injectors import PerformanceMetrics

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Result of comparing fault injection vs baseline execution"""
    scenario_id: int
    scenario_name: str
    fault_metrics: PerformanceMetrics
    baseline_metrics: PerformanceMetrics
    
    # Delta calculations
    latency_delta_ms: float = 0.0
    latency_delta_percent: float = 0.0
    token_delta: int = 0
    token_delta_percent: float = 0.0
    cost_delta_usd: float = 0.0
    cost_delta_percent: float = 0.0
    tool_call_delta: int = 0
    
    # Root cause analysis
    root_cause: str = ""
    impact_summary: str = ""
    recommendation: str = ""
    
    def __post_init__(self):
        """Calculate deltas after initialization"""
        self._calculate_deltas()
        self._generate_root_cause_analysis()
    
    def _calculate_deltas(self):
        """Calculate performance deltas"""
        # Latency delta
        self.latency_delta_ms = self.fault_metrics.latency_ms - self.baseline_metrics.latency_ms
        if self.baseline_metrics.latency_ms > 0:
            self.latency_delta_percent = (self.latency_delta_ms / self.baseline_metrics.latency_ms) * 100
        
        # Token delta
        self.token_delta = self.fault_metrics.total_tokens - self.baseline_metrics.total_tokens
        if self.baseline_metrics.total_tokens > 0:
            self.token_delta_percent = (self.token_delta / self.baseline_metrics.total_tokens) * 100
        
        # Cost delta
        self.cost_delta_usd = self.fault_metrics.estimated_cost_usd - self.baseline_metrics.estimated_cost_usd
        if self.baseline_metrics.estimated_cost_usd > 0:
            self.cost_delta_percent = (self.cost_delta_usd / self.baseline_metrics.estimated_cost_usd) * 100
        
        # Tool call delta
        self.tool_call_delta = self.fault_metrics.tool_calls - self.baseline_metrics.tool_calls
    
    def _generate_root_cause_analysis(self):
        """Generate root cause analysis based on deltas"""
        causes = []
        
        # Analyze latency impact
        if self.fault_metrics.injected_latency_ms > 0:
            causes.append(f"Injected latency: +{self.fault_metrics.injected_latency_ms:.0f}ms")
        
        # Analyze token bloat
        if self.fault_metrics.bloat_tokens > 0:
            causes.append(f"Context bloat: +{self.fault_metrics.bloat_tokens} tokens")
        
        # Analyze tool calls
        if self.tool_call_delta > 0:
            causes.append(f"Redundant tool calls: +{self.tool_call_delta} calls")
        elif self.tool_call_delta < 0:
            causes.append(f"Reduced tool calls: {self.tool_call_delta} calls")
        
        # Analyze errors
        if self.fault_metrics.error_count > 0:
            causes.append(f"Errors encountered: {self.fault_metrics.error_count}")
        
        # Analyze retries
        if self.fault_metrics.retry_count > 0:
            causes.append(f"Retry attempts: {self.fault_metrics.retry_count}")
        
        self.root_cause = " | ".join(causes) if causes else "No significant fault injection detected"
        
        # Generate impact summary
        self.impact_summary = self._generate_impact_summary()
        
        # Generate recommendation
        self.recommendation = self._generate_recommendation()
    
    def _generate_impact_summary(self) -> str:
        """Generate human-readable impact summary"""
        impacts = []
        
        if abs(self.latency_delta_percent) > 10:
            direction = "slower" if self.latency_delta_ms > 0 else "faster"
            impacts.append(f"{abs(self.latency_delta_percent):.0f}% {direction}")
        
        if abs(self.cost_delta_percent) > 10:
            direction = "more expensive" if self.cost_delta_usd > 0 else "cheaper"
            impacts.append(f"{abs(self.cost_delta_percent):.0f}% {direction}")
        
        if abs(self.token_delta_percent) > 10:
            direction = "more tokens" if self.token_delta > 0 else "fewer tokens"
            impacts.append(f"{abs(self.token_delta_percent):.0f}% {direction}")
        
        return ", ".join(impacts) if impacts else "Minimal performance impact"
    
    def _generate_recommendation(self) -> str:
        """Generate optimization recommendation"""
        if self.fault_metrics.bloat_tokens > 1000:
            return "Reduce context size through summarization or pruning"
        elif self.tool_call_delta > 1:
            return "Bundle tool calls to reduce latency overhead"
        elif self.fault_metrics.injected_latency_ms > 1000:
            return "Optimize external service calls or implement caching"
        elif self.fault_metrics.error_count > 0:
            return "Implement error handling and retry logic"
        else:
            return "Performance is within acceptable range"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'scenario_id': self.scenario_id,
            'scenario_name': self.scenario_name,
            'fault_metrics': self.fault_metrics.to_dict(),
            'baseline_metrics': self.baseline_metrics.to_dict(),
            'deltas': {
                'latency_ms': self.latency_delta_ms,
                'latency_percent': self.latency_delta_percent,
                'tokens': self.token_delta,
                'tokens_percent': self.token_delta_percent,
                'cost_usd': self.cost_delta_usd,
                'cost_percent': self.cost_delta_percent,
                'tool_calls': self.tool_call_delta
            },
            'analysis': {
                'root_cause': self.root_cause,
                'impact_summary': self.impact_summary,
                'recommendation': self.recommendation
            }
        }


class MetricsCollector:
    """
    Collects and aggregates metrics using AgentCore observability.
    
    AgentCore provides automatic:
    - CloudWatch metrics for latency, token usage, tool calls, errors
    - X-Ray trace segments for each tool invocation and LLM call
    - Structured JSON logs to CloudWatch Logs with execution context
    """
    
    def __init__(self):
        """Initialize metrics collector"""
        logger.info("MetricsCollector initialized - leveraging AgentCore observability")
    
    def collect_execution_metrics(self, context: Any) -> PerformanceMetrics:
        """
        Collect metrics from agent execution context.
        
        AgentCore automatically emits:
        - Custom CloudWatch metrics
        - X-Ray trace segments
        - Structured logs
        
        Args:
            context: Agent execution context
            
        Returns:
            PerformanceMetrics collected from execution
        """
        # In production, this would extract metrics from AgentCore context
        # For now, return the metrics from context
        if hasattr(context, 'metrics'):
            logger.debug(f"Collected metrics: {context.metrics.latency_ms}ms, {context.metrics.total_tokens} tokens")
            return context.metrics
        
        # Fallback metrics
        return PerformanceMetrics(
            latency_ms=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            tool_calls=0
        )
    
    def compare_executions(self, scenario_id: int, scenario_name: str, 
                          fault_metrics: PerformanceMetrics, 
                          baseline_metrics: PerformanceMetrics) -> ComparisonResult:
        """
        Compare fault injection vs baseline execution.
        
        Args:
            scenario_id: Scenario identifier
            scenario_name: Scenario name
            fault_metrics: Metrics from fault injection execution
            baseline_metrics: Metrics from baseline execution
            
        Returns:
            ComparisonResult with deltas and analysis
        """
        logger.info(f"Comparing executions for scenario {scenario_id}: {scenario_name}")
        
        result = ComparisonResult(
            scenario_id=scenario_id,
            scenario_name=scenario_name,
            fault_metrics=fault_metrics,
            baseline_metrics=baseline_metrics
        )
        
        logger.info(f"  Latency delta: {result.latency_delta_ms:.0f}ms ({result.latency_delta_percent:.1f}%)")
        logger.info(f"  Token delta: {result.token_delta} ({result.token_delta_percent:.1f}%)")
        logger.info(f"  Cost delta: ${result.cost_delta_usd:.4f} ({result.cost_delta_percent:.1f}%)")
        logger.info(f"  Root cause: {result.root_cause}")
        
        return result
    
    def emit_custom_metric(self, metric_name: str, value: float, unit: str = "None", 
                          dimensions: Optional[Dict[str, str]] = None):
        """
        Emit custom CloudWatch metric.
        
        In production, this would use boto3 CloudWatch client.
        AgentCore automatically emits standard metrics.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: CloudWatch unit (None, Count, Milliseconds, etc.)
            dimensions: Metric dimensions
        """
        logger.debug(f"Would emit CloudWatch metric: {metric_name}={value} {unit}")
        if dimensions:
            logger.debug(f"  Dimensions: {dimensions}")
    
    def create_trace_segment(self, segment_name: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Create X-Ray trace segment.
        
        In production, this would use AWS X-Ray SDK.
        AgentCore automatically creates trace segments for tool calls.
        
        Args:
            segment_name: Name of the trace segment
            metadata: Additional metadata to attach
        """
        logger.debug(f"Would create X-Ray segment: {segment_name}")
        if metadata:
            logger.debug(f"  Metadata: {json.dumps(metadata, indent=2)}")
    
    def log_structured_event(self, event_type: str, event_data: Dict[str, Any]):
        """
        Log structured event to CloudWatch Logs.
        
        AgentCore automatically logs structured JSON with execution context.
        
        Args:
            event_type: Type of event
            event_data: Event data dictionary
        """
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'data': event_data
        }
        logger.info(f"Structured log: {json.dumps(log_entry)}")
    
    def query_agentcore_observability(self, scenario_id: int, time_range_minutes: int = 60) -> Dict[str, Any]:
        """
        Query AgentCore observability data from CloudWatch.
        
        In production, this would:
        - Use CloudWatch Insights to query AgentCore logs
        - Use X-Ray API to retrieve AgentCore trace data
        - Use Application Signals for service-level metrics
        
        Args:
            scenario_id: Scenario to query data for
            time_range_minutes: Time range to query
            
        Returns:
            Dictionary with observability data
        """
        logger.info(f"Would query AgentCore observability data for scenario {scenario_id}")
        logger.info(f"  Time range: last {time_range_minutes} minutes")
        logger.info("  Data sources: CloudWatch Logs, X-Ray, Application Signals")
        
        # Placeholder return
        return {
            'scenario_id': scenario_id,
            'logs_found': 0,
            'traces_found': 0,
            'metrics_found': 0
        }


# Global metrics collector instance
metrics_collector = MetricsCollector()
