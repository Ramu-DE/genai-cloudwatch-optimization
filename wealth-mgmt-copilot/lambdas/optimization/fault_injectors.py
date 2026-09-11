"""
Fault Injectors for Wealth Management Agent Performance Testing

Provides the base FaultInjector abstract class and common infrastructure
for implementing fault injection scenarios against financial advisory agents.
"""

import logging
import time
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Pricing constants (per 1K tokens)
# ============================================================================
MODEL_PRICING = {
    'us.anthropic.claude-haiku-4-5-20251001-v1:0': {
        'input_per_1k': 0.00080,
        'output_per_1k': 0.00400,
        'label': 'Haiku 4.5'
    },
    'us.anthropic.claude-sonnet-4-20250514-v1:0': {
        'input_per_1k': 0.00300,
        'output_per_1k': 0.01500,
        'label': 'Sonnet 4'
    },
    'default': {
        'input_per_1k': 0.00080,
        'output_per_1k': 0.00400,
        'label': 'default'
    }
}


def estimate_cost(input_tokens: int, output_tokens: int,
                  model_id: str = 'us.anthropic.claude-haiku-4-5-20251001-v1:0') -> float:
    pricing = MODEL_PRICING.get(model_id, MODEL_PRICING['default'])
    return (input_tokens / 1000) * pricing['input_per_1k'] + \
           (output_tokens / 1000) * pricing['output_per_1k']


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class PerformanceMetrics:
    """Performance metrics collected during agent execution"""
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0
    tool_call_breakdown: Dict[str, int] = field(default_factory=dict)
    estimated_cost_usd: float = 0.0
    model_id: str = ''
    timestamp: datetime = field(default_factory=datetime.utcnow)
    scenario_id: Optional[int] = None

    # Fault injection analysis fields
    injected_latency_ms: float = 0.0
    bloat_tokens: int = 0
    error_count: int = 0
    retry_count: int = 0
    cache_hits: int = 0
    cache_misses: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'latency_ms': round(self.latency_ms, 2),
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'tool_calls': self.tool_calls,
            'tool_call_breakdown': self.tool_call_breakdown,
            'estimated_cost_usd': round(self.estimated_cost_usd, 6),
            'model_id': self.model_id,
            'timestamp': self.timestamp.isoformat(),
            'scenario_id': self.scenario_id,
            'injected_latency_ms': round(self.injected_latency_ms, 2),
            'bloat_tokens': self.bloat_tokens,
            'error_count': self.error_count,
            'retry_count': self.retry_count,
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
        }


@dataclass
class AgentContext:
    """Context for agent execution with fault injection capabilities"""
    user_input: str
    client_id: str
    session_id: str
    system_prompt: str
    tools: List[Any]
    metrics: PerformanceMetrics
    scenario_config: Optional[Any] = None

    execution_start_time: Optional[float] = None
    execution_end_time: Optional[float] = None

    fault_injected: bool = False
    fault_description: str = ""

    agent_response: str = ""
    error_message: Optional[str] = None

    def start_execution(self):
        self.execution_start_time = time.time()

    def end_execution(self):
        self.execution_end_time = time.time()
        if self.execution_start_time:
            self.metrics.latency_ms = (self.execution_end_time - self.execution_start_time) * 1000

    def add_metric(self, key: str, value: Any):
        if hasattr(self.metrics, key):
            setattr(self.metrics, key, value)


# ============================================================================
# Exceptions
# ============================================================================

class FaultInjectionError(Exception):
    pass

class ScenarioNotFoundError(FaultInjectionError):
    pass

class MetricsCollectionError(FaultInjectionError):
    pass


# ============================================================================
# Abstract base
# ============================================================================

class FaultInjector(ABC):
    """Abstract base class for fault injection implementations."""

    def __init__(self, scenario_id: int, scenario_name: str,
                 fault_config: Optional[Dict[str, Any]] = None):
        self.scenario_id = scenario_id
        self.scenario_name = scenario_name
        self.fault_config = fault_config or {}
        logger.info(f"Initialized {self.__class__.__name__} for scenario {scenario_id}: {scenario_name}")

    @abstractmethod
    def inject_fault(self, context: AgentContext) -> AgentContext:
        pass

    @abstractmethod
    def get_baseline_metrics(self) -> PerformanceMetrics:
        pass

    def log_fault_injection(self, context: AgentContext, fault_description: str):
        context.fault_injected = True
        context.fault_description = fault_description
        logger.info(f"Fault injected — scenario {self.scenario_id}: {fault_description}")

    def collect_metrics(self, context: AgentContext) -> PerformanceMetrics:
        context.end_execution()
        return context.metrics


# ============================================================================
# Bloat generators (wealth-management specific)
# ============================================================================

def generate_raw_transaction_history(tokens: int = 8000) -> str:
    """Generate realistic raw trade history to bloat context."""
    tickers = ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'NVDA', 'TSLA', 'JPM',
               'BND', 'VTI', 'SCHD', 'GLD', 'VIG', 'MUB', 'TLT', 'AMD']
    actions = ['BUY', 'SELL', 'DIVIDEND', 'SPLIT']
    lines = []
    target_chars = tokens * 4  # ~4 chars per token
    while len('\n'.join(lines)) < target_chars:
        dt = f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}T{random.randint(9,16):02d}:{random.randint(0,59):02d}:00Z"
        ticker = random.choice(tickers)
        action = random.choice(actions)
        shares = random.randint(1, 500)
        price = round(random.uniform(20, 450), 2)
        total = round(shares * price, 2)
        lines.append(
            f"{{\"date\":\"{dt}\",\"ticker\":\"{ticker}\",\"action\":\"{action}\","
            f"\"shares\":{shares},\"price\":{price},\"total\":{total},"
            f"\"commission\":4.95,\"settlement\":\"T+2\",\"account\":\"taxable\","
            f"\"order_type\":\"MARKET\",\"fill_quality\":\"FULL\",\"exchange\":\"NYSE\"}}"
        )
    return "RAW TRANSACTION DUMP:\n" + '\n'.join(lines)


def generate_irrelevant_crm_fields(tokens: int = 8000) -> str:
    """Generate irrelevant CRM data that should never be in a portfolio prompt."""
    target_chars = tokens * 4
    filler = (
        "Browser: Chrome 120.0 | Last login IP: 192.168.1.42 | Marketing opt-in: true | "
        "Referral source: Google Ads campaign_id=camp_8827 | Support tickets: #4401 password "
        "reset 2024-01-15, #4822 address update 2024-03-22 | Cookie consent: accepted "
        "2023-11-01 | Preferred language: en-US | Time zone: America/New_York | "
        "Email open rate: 42% | Last newsletter click: 2024-08-01 | NPS score: 8 | "
        "App version: 3.2.1 | Device: iPhone 15 Pro | Two-factor: enabled | "
        "Last password change: 2024-06-15 | Failed login attempts: 0 | "
        "Marketing segment: high-value-engaged | A/B test group: variant_b | "
        "Push notifications: enabled | Data export requests: 0 | GDPR consent date: 2023-01-01\n"
    )
    repeat_count = (target_chars // len(filler)) + 1
    return "FULL CRM RECORD:\n" + (filler * repeat_count)[:target_chars]


def generate_raw_market_feed(tokens: int = 5000) -> str:
    """Generate unprocessed market feed data."""
    target_chars = tokens * 4
    lines = []
    tickers = ['NVDA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL']
    while len('\n'.join(lines)) < target_chars:
        t = random.choice(tickers)
        ts = f"2024-09-15T{random.randint(9,15):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}.{random.randint(0,999):03d}Z"
        o = round(random.uniform(100, 300), 4)
        h = round(o * 1.02, 4)
        l = round(o * 0.98, 4)
        c = round(random.uniform(l, h), 4)
        v = random.randint(100, 50000)
        lines.append(
            f"{{\"ts\":\"{ts}\",\"sym\":\"{t}\",\"o\":{o},\"h\":{h},\"l\":{l},"
            f"\"c\":{c},\"v\":{v},\"vwap\":{round(c*0.999,4)},\"bid\":{round(c-0.01,4)},"
            f"\"ask\":{round(c+0.01,4)},\"spread\":0.02,\"trades\":{random.randint(1,200)}}}"
        )
    return "RAW MARKET FEED:\n" + '\n'.join(lines)


def generate_useless_memory_summary() -> str:
    """Generate a misleading memory summary that contradicts actual data."""
    return (
        "PREVIOUS SESSION SUMMARY (retrieved from memory):\n"
        "Client indicated they want to move everything to cash and close all positions. "
        "They expressed extreme risk aversion after a family emergency. "
        "They asked us to cancel all pending trades and liquidate the tech holdings. "
        "They said they no longer trust the market and want 100% in savings. "
        "NOTE: Client was very emotional and requested no further contact for 30 days.\n"
        "---\n"
        "WARNING: The above summary is STALE and may not reflect current intent.\n"
    )


def generate_extreme_compliance_history(tokens: int = 15000) -> str:
    """Generate extreme-length compliance history for token limit testing."""
    target_chars = tokens * 4
    events = []
    event_types = ['KYC_CHECK', 'AML_SCAN', 'TRANSACTION_REVIEW', 'SUITABILITY_ASSESSMENT',
                   'RISK_LIMIT_CHECK', 'DOCUMENT_VERIFICATION', 'AUDIT_ENTRY',
                   'REGULATORY_FILING', 'CLIENT_COMPLAINT', 'ESCALATION']
    statuses = ['PASSED', 'FLAGGED', 'PENDING', 'CLEARED', 'ESCALATED']
    while len('\n'.join(events)) < target_chars:
        dt = f"2023-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
        et = random.choice(event_types)
        st = random.choice(statuses)
        events.append(
            f"{{\"date\":\"{dt}\",\"type\":\"{et}\",\"status\":\"{st}\","
            f"\"reviewer\":\"compliance_team\",\"notes\":\"Routine {et.lower().replace('_',' ')} "
            f"completed. All documentation verified. No issues found. Reference: REF-{random.randint(10000,99999)}\","
            f"\"risk_score\":{round(random.uniform(0.1,0.9),2)},\"regulatory_body\":\"SEC\"}}"
        )
    return "FULL COMPLIANCE HISTORY:\n" + '\n'.join(events)
