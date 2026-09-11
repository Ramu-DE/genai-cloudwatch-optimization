#!/usr/bin/env python3
"""
Olivia Tax Optimizer Agent - CrewAI on Bedrock AgentCore
Tax-loss harvesting, capital gains optimization, bracket management, and year-end planning.
"""
import os
import sys
import logging
import boto3
import json
import time
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel
from bedrock_agentcore.runtime import BedrockAgentCoreApp

# CloudWatch Custom Metrics
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
    from metrics_emitter import MetricsEmitter
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.expanduser('~'), 'olivia_agent.log'),
            mode='a', encoding='utf-8',
        ),
    ],
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger.info("TAX OPTIMIZER AGENT STARTING UP - OLIVIA")
logger.info(f"Python version: {sys.version}")
logger.info(f"AWS Region: {os.environ.get('AWS_REGION', 'us-west-2')}")

# --- CrewAI imports (used inside the entrypoint) --------------------------------
try:
    from crewai import Agent as CrewAgent, Task as CrewTask, Crew, Process
    CREWAI_AVAILABLE = True
    logger.info("CrewAI framework available")
except ImportError:
    CREWAI_AVAILABLE = False
    logger.warning("CrewAI not installed - falling back to Strands-only mode")

# --- AgentCore Memory -----------------------------------------------------------
try:
    from bedrock_agentcore.memory import MemoryClient
    from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider
    MEMORY_AVAILABLE = True
    MEMORY_TOOLS_AVAILABLE = True
    logger.info("AgentCore Memory and Tools available")
except ImportError:
    try:
        from bedrock_agentcore.memory import MemoryClient
        MEMORY_AVAILABLE = True
        MEMORY_TOOLS_AVAILABLE = False
        logger.info("AgentCore Memory available (no tools)")
    except ImportError:
        MEMORY_AVAILABLE = False
        MEMORY_TOOLS_AVAILABLE = False
        logger.warning("AgentCore Memory not available")

# --- AgentCore App ---------------------------------------------------------------
app = BedrockAgentCoreApp()

# --- AWS config ------------------------------------------------------------------
AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')
MODEL_ID = os.environ.get(
    'BEDROCK_MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
)

# Initialize metrics emitter
metrics = MetricsEmitter(agent_name='olivia', model_id=MODEL_ID) if METRICS_AVAILABLE else None

dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)

TABLES = {
    'clients': 'wealth_mgmt_client_profiles',
    'portfolios': 'wealth_mgmt_portfolios',
    'transactions': 'wealth_mgmt_transactions',
    'tax_records': 'wealth_mgmt_tax_records',
    'user_auth': 'wealth_mgmt_user_auth',
}

# --- Globals for memory ----------------------------------------------------------
memory_client = None
memory_id = None
memory_tool_provider = None

# =============================================================================
# UTILITIES
# =============================================================================

def decimal_to_native(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimal_to_native(v) for v in obj]
    return obj


def log_dynamodb_request(operation: str, table_name: str, key: dict = None, item: dict = None):
    logger.info("=" * 80)
    logger.info("DYNAMODB REQUEST START")
    logger.info(f"Operation: {operation} | Table: {table_name}")
    logger.info(f"Key: {json.dumps(key, default=str) if key else 'None'}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")


def log_dynamodb_response(operation: str, response: dict, duration: float):
    logger.info(f"DYNAMODB RESPONSE | Operation: {operation} | Duration: {duration:.3f}s")
    logger.info(
        f"HTTP Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode', '?')}"
    )
    logger.info("DYNAMODB REQUEST COMPLETE")
    logger.info("=" * 80)

# =============================================================================
# MOCK / FALLBACK DATA
# =============================================================================

MOCK_TAX_PROFILES = {
    "client_sarah_chen": {
        "name": "Sarah Chen",
        "filing_status": "Married Filing Jointly",
        "tax_bracket": "32%",
        "marginal_rate": 0.32,
        "estimated_agi": 450000,
        "state": "CA",
        "state_rate": 0.093,
        "ytd_federal_tax_paid": 95000,
        "ytd_state_tax_paid": 28000,
        "deductions": {
            "mortgage_interest": 18500,
            "property_tax": 10000,
            "charitable": 12000,
            "salt_cap": 10000,
        },
        "retirement_contributions": {
            "401k": 23000,
            "ira": 7000,
            "hsa": 8300,
        },
    },
    "client_james_wilson": {
        "name": "James Wilson",
        "filing_status": "Single",
        "tax_bracket": "24%",
        "marginal_rate": 0.24,
        "estimated_agi": 180000,
        "state": "TX",
        "state_rate": 0.0,
        "ytd_federal_tax_paid": 32000,
        "ytd_state_tax_paid": 0,
        "deductions": {
            "mortgage_interest": 9200,
            "property_tax": 6000,
            "charitable": 3500,
            "salt_cap": 10000,
        },
        "retirement_contributions": {
            "401k": 23000,
            "ira": 7000,
            "hsa": 4150,
        },
    },
    "client_maria_garcia": {
        "name": "Maria Garcia",
        "filing_status": "Head of Household",
        "tax_bracket": "35%",
        "marginal_rate": 0.35,
        "estimated_agi": 520000,
        "state": "NY",
        "state_rate": 0.0685,
        "ytd_federal_tax_paid": 125000,
        "ytd_state_tax_paid": 30000,
        "deductions": {
            "mortgage_interest": 24000,
            "property_tax": 15000,
            "charitable": 45000,
            "salt_cap": 10000,
        },
        "retirement_contributions": {
            "401k": 23000,
            "ira": 0,
            "hsa": 4150,
        },
    },
}

MOCK_PORTFOLIO_POSITIONS = {
    "client_sarah_chen": [
        {"ticker": "AAPL", "shares": 150, "cost_basis": 142.50, "current_price": 178.30, "purchase_date": "2023-03-15", "holding_period": "long_term", "unrealized_gain": 5370.00},
        {"ticker": "MSFT", "shares": 80, "cost_basis": 380.00, "current_price": 415.20, "purchase_date": "2023-06-20", "holding_period": "long_term", "unrealized_gain": 2816.00},
        {"ticker": "TSLA", "shares": 50, "cost_basis": 265.00, "current_price": 198.50, "purchase_date": "2024-01-10", "holding_period": "long_term", "unrealized_gain": -3325.00},
        {"ticker": "NVDA", "shares": 60, "cost_basis": 480.00, "current_price": 725.00, "purchase_date": "2024-05-01", "holding_period": "long_term", "unrealized_gain": 14700.00},
        {"ticker": "AMZN", "shares": 100, "cost_basis": 185.00, "current_price": 178.40, "purchase_date": "2026-04-15", "holding_period": "short_term", "unrealized_gain": -660.00},
        {"ticker": "META", "shares": 40, "cost_basis": 510.00, "current_price": 485.00, "purchase_date": "2026-06-01", "holding_period": "short_term", "unrealized_gain": -1000.00},
        {"ticker": "VTI", "shares": 200, "cost_basis": 220.00, "current_price": 258.70, "purchase_date": "2022-01-15", "holding_period": "long_term", "unrealized_gain": 7740.00},
        {"ticker": "BND", "shares": 300, "cost_basis": 72.50, "current_price": 71.80, "purchase_date": "2023-09-01", "holding_period": "long_term", "unrealized_gain": -210.00},
    ],
    "client_james_wilson": [
        {"ticker": "GOOGL", "shares": 70, "cost_basis": 140.00, "current_price": 172.50, "purchase_date": "2023-11-20", "holding_period": "long_term", "unrealized_gain": 2275.00},
        {"ticker": "INTC", "shares": 200, "cost_basis": 42.00, "current_price": 31.50, "purchase_date": "2024-02-10", "holding_period": "long_term", "unrealized_gain": -2100.00},
        {"ticker": "DIS", "shares": 100, "cost_basis": 112.00, "current_price": 98.50, "purchase_date": "2024-08-15", "holding_period": "long_term", "unrealized_gain": -1350.00},
        {"ticker": "SPY", "shares": 50, "cost_basis": 470.00, "current_price": 545.00, "purchase_date": "2023-07-01", "holding_period": "long_term", "unrealized_gain": 3750.00},
        {"ticker": "QQQ", "shares": 30, "cost_basis": 485.00, "current_price": 460.00, "purchase_date": "2026-07-20", "holding_period": "short_term", "unrealized_gain": -750.00},
    ],
    "client_maria_garcia": [
        {"ticker": "AAPL", "shares": 300, "cost_basis": 155.00, "current_price": 178.30, "purchase_date": "2022-06-15", "holding_period": "long_term", "unrealized_gain": 6990.00},
        {"ticker": "JPM", "shares": 150, "cost_basis": 165.00, "current_price": 198.50, "purchase_date": "2023-01-10", "holding_period": "long_term", "unrealized_gain": 5025.00},
        {"ticker": "PFE", "shares": 500, "cost_basis": 38.00, "current_price": 28.50, "purchase_date": "2023-04-20", "holding_period": "long_term", "unrealized_gain": -4750.00},
        {"ticker": "BA", "shares": 80, "cost_basis": 220.00, "current_price": 185.00, "purchase_date": "2024-03-01", "holding_period": "long_term", "unrealized_gain": -2800.00},
        {"ticker": "SCHD", "shares": 400, "cost_basis": 75.00, "current_price": 82.40, "purchase_date": "2022-09-01", "holding_period": "long_term", "unrealized_gain": 2960.00},
        {"ticker": "NFLX", "shares": 25, "cost_basis": 680.00, "current_price": 620.00, "purchase_date": "2026-05-10", "holding_period": "short_term", "unrealized_gain": -1500.00},
    ],
}

FEDERAL_BRACKETS_2026_MFJ = [
    (23850, 0.10), (97100, 0.12), (206700, 0.22),
    (394600, 0.24), (501050, 0.32), (751600, 0.35),
    (float('inf'), 0.37),
]

FEDERAL_BRACKETS_2026_SINGLE = [
    (11925, 0.10), (48475, 0.12), (103350, 0.22),
    (197300, 0.24), (250525, 0.32), (375800, 0.35),
    (float('inf'), 0.37),
]

FEDERAL_BRACKETS_2026_HOH = [
    (17000, 0.10), (64850, 0.12), (103350, 0.22),
    (197300, 0.24), (250500, 0.32), (375800, 0.35),
    (float('inf'), 0.37),
]

LTCG_RATES = {
    "0%": {"single": 47025, "mfj": 94050, "hoh": 63000},
    "15%": {"single": 518900, "mfj": 583750, "hoh": 551350},
    "20%": {"single": float('inf'), "mfj": float('inf'), "hoh": float('inf')},
}

# =============================================================================
# MEMORY MANAGEMENT
# =============================================================================

def initialize_memory(client_id=None, session_id=None):
    global memory_client, memory_id
    if not MEMORY_AVAILABLE:
        logger.warning("AgentCore Memory not available")
        return None

    target_memory_id = os.getenv(
        'BEDROCK_AGENTCORE_MEMORY_ID',
        'wealth_mgmt_olivia_tax_optimizer_agent_memory',
    )

    if memory_id:
        logger.info(f"Using cached memory ID: {memory_id}")
        return memory_id

    try:
        memory_client = MemoryClient(region_name=AWS_REGION)

        try:
            memories = memory_client.list_memories()
            for m in memories:
                mid = m.get('id')
                if mid and target_memory_id in mid:
                    memory_id = mid
                    logger.info(f"Found existing memory: {memory_id}")
                    return memory_id
        except Exception as e:
            logger.warning(f"Error listing memories: {e}")

        try:
            memory = memory_client.create_memory_and_wait(
                name=target_memory_id,
                description="Unified persistent memory for Olivia tax optimizer agent",
                strategies=[
                    {
                        "summaryMemoryStrategy": {
                            "name": "TaxSessionSummarizer",
                            "description": "Summarizes tax planning consultations across all clients",
                            "namespaces": ["/summaries/olivia/{actorId}/{sessionId}"],
                        }
                    },
                    {
                        "semanticMemoryStrategy": {
                            "name": "TaxKnowledgeBase",
                            "description": "Stores tax rules, strategies, and client-specific tax facts",
                            "namespaces": ["/knowledge/olivia/{actorId}/tax"],
                        }
                    },
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": "TaxPreferences",
                            "description": "Learns client tax planning preferences and risk tolerance",
                            "namespaces": ["/preferences/olivia/{actorId}"],
                        }
                    },
                ],
                event_expiry_days=5,
            )
            memory_id = memory.get('id') or memory.get('memoryId')
            logger.info(f"Memory created: {memory_id}")
            return memory_id
        except Exception as create_error:
            if "already exists" in str(create_error):
                try:
                    memories = memory_client.list_memories()
                    for m in memories:
                        mid = m.get('id')
                        if mid and target_memory_id in mid:
                            memory_id = mid
                            return memory_id
                except Exception:
                    pass
            logger.error(f"Could not set up memory: {create_error}")
            return None
    except Exception as e:
        logger.error(f"Could not set up AgentCore Memory: {e}")
        return None


def initialize_memory_tools(client_id, session_id=None):
    global memory_tool_provider, memory_id
    if not MEMORY_TOOLS_AVAILABLE or not memory_id:
        return None
    try:
        namespace = f"/preferences/olivia/{client_id}"
        memory_tool_provider = AgentCoreMemoryToolProvider(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id or "default",
            namespace=namespace,
            region=AWS_REGION,
        )
        logger.info(f"Memory tool provider initialized for {client_id}")
        return memory_tool_provider
    except Exception as e:
        logger.error(f"Could not initialize memory tool provider: {e}")
        return None


def save_conversation_to_memory(client_id, session_id, user_message, agent_response):
    global memory_client, memory_id
    if not memory_id or not memory_client:
        return
    try:
        max_length = 8500
        truncated_user = user_message[:max_length] + "... [truncated]" if len(user_message) > max_length else user_message
        truncated_resp = agent_response[:max_length] + "... [truncated]" if len(agent_response) > max_length else agent_response

        memory_client.create_event(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
            messages=[
                (truncated_user, "user"),
                (truncated_resp, "assistant"),
            ],
        )
        logger.info("Conversation saved to memory")
    except Exception as e:
        logger.error(f"Could not save to memory: {e}")


def get_conversation_context(client_id, session_id):
    global memory_client, memory_id
    if not memory_id or not memory_client:
        initialize_memory(client_id, session_id)
    if not memory_id or not memory_client:
        return ""
    try:
        events = memory_client.list_events(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
        )
        if not events:
            return ""
        recent_turns = memory_client.get_last_k_turns(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
            k=5,
        )
        if not recent_turns:
            return ""
        context_parts = []
        for turn in recent_turns:
            role = turn.get('role', 'unknown')
            content = turn.get('content', '')
            if content:
                context_parts.append(f"{role}: {content[:300]}")
        return "\n".join(context_parts)
    except Exception as e:
        logger.warning(f"Could not retrieve conversation context: {e}")
        return ""

# =============================================================================
# DynamoDB HELPERS
# =============================================================================

def get_client_tax_data(client_id: str):
    """Fetch client tax profile from DynamoDB, falling back to mock data."""
    try:
        table = dynamodb_resource.Table(TABLES['clients'])
        log_dynamodb_request('GetItem', TABLES['clients'], key={'client_id': client_id})
        start = time.time()
        response = table.get_item(Key={'client_id': client_id})
        log_dynamodb_response('GetItem', response, time.time() - start)
        item = response.get('Item')
        if item:
            return decimal_to_native(item)
    except Exception as e:
        logger.warning(f"DynamoDB lookup failed for {client_id}: {e}")

    if client_id in MOCK_TAX_PROFILES:
        logger.info(f"Using mock tax profile for {client_id}")
        return MOCK_TAX_PROFILES[client_id]
    return None


def get_client_positions(client_id: str):
    """Fetch portfolio positions from DynamoDB, falling back to mock data."""
    try:
        table = dynamodb_resource.Table(TABLES['portfolios'])
        log_dynamodb_request('Query', TABLES['portfolios'], key={'client_id': client_id})
        start = time.time()
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('client_id').eq(client_id),
        )
        log_dynamodb_response('Query', response, time.time() - start)
        items = response.get('Items', [])
        if items:
            return [decimal_to_native(i) for i in items]
    except Exception as e:
        logger.warning(f"DynamoDB portfolio lookup failed for {client_id}: {e}")

    if client_id in MOCK_PORTFOLIO_POSITIONS:
        logger.info(f"Using mock portfolio for {client_id}")
        return MOCK_PORTFOLIO_POSITIONS[client_id]
    return []

# =============================================================================
# STRANDS TOOLS (DynamoDB-backed, exposed to the agent)
# =============================================================================

@tool
def get_client_tax_profile(client_id: str):
    """Get client tax profile including bracket, filing status, deductions, and retirement contributions."""
    try:
        profile = get_client_tax_data(client_id)
        if not profile:
            return f"Client {client_id} not found. Please verify the client ID."

        info = f"""Client Tax Profile:
- Name: {profile.get('name', 'Unknown')}
- Filing Status: {profile.get('filing_status', 'Unknown')}
- Federal Tax Bracket: {profile.get('tax_bracket', 'Unknown')}
- Marginal Rate: {profile.get('marginal_rate', 0):.0%}
- Estimated AGI: ${profile.get('estimated_agi', 0):,.0f}
- State: {profile.get('state', 'Unknown')} (State Rate: {profile.get('state_rate', 0):.1%})

YTD Taxes Paid:
- Federal: ${profile.get('ytd_federal_tax_paid', 0):,.0f}
- State: ${profile.get('ytd_state_tax_paid', 0):,.0f}

Deductions:
- Mortgage Interest: ${profile.get('deductions', {}).get('mortgage_interest', 0):,.0f}
- Property Tax: ${profile.get('deductions', {}).get('property_tax', 0):,.0f}
- Charitable Giving: ${profile.get('deductions', {}).get('charitable', 0):,.0f}
- SALT Cap Applied: ${profile.get('deductions', {}).get('salt_cap', 10000):,.0f}

Retirement Contributions (YTD):
- 401(k): ${profile.get('retirement_contributions', {}).get('401k', 0):,.0f}
- IRA: ${profile.get('retirement_contributions', {}).get('ira', 0):,.0f}
- HSA: ${profile.get('retirement_contributions', {}).get('hsa', 0):,.0f}"""
        return info
    except Exception as e:
        return f"Error retrieving tax profile: {str(e)}"


@tool
def find_harvesting_opportunities(client_id: str):
    """Scan portfolio for tax-loss harvesting opportunities - positions with unrealized losses."""
    try:
        positions = get_client_positions(client_id)
        if not positions:
            return f"No portfolio positions found for {client_id}."

        profile = get_client_tax_data(client_id)
        marginal_rate = profile.get('marginal_rate', 0.24) if profile else 0.24

        losses_st = []
        losses_lt = []
        gains_st = []
        gains_lt = []

        for pos in positions:
            gain = pos.get('unrealized_gain', (pos['current_price'] - pos['cost_basis']) * pos['shares'])
            entry = {
                "ticker": pos['ticker'],
                "shares": pos['shares'],
                "cost_basis": pos['cost_basis'],
                "current_price": pos['current_price'],
                "unrealized": gain,
                "holding_period": pos.get('holding_period', 'long_term'),
            }
            if gain < 0:
                (losses_st if entry['holding_period'] == 'short_term' else losses_lt).append(entry)
            else:
                (gains_st if entry['holding_period'] == 'short_term' else gains_lt).append(entry)

        total_harvestable = sum(abs(p['unrealized']) for p in losses_st + losses_lt)
        st_loss_total = sum(abs(p['unrealized']) for p in losses_st)
        lt_loss_total = sum(abs(p['unrealized']) for p in losses_lt)
        st_gain_total = sum(p['unrealized'] for p in gains_st)
        lt_gain_total = sum(p['unrealized'] for p in gains_lt)

        result = f"""Tax-Loss Harvesting Analysis for {client_id}:

HARVESTING OPPORTUNITIES (Positions with Unrealized Losses):
"""
        for p in sorted(losses_st + losses_lt, key=lambda x: x['unrealized']):
            tax_saving = abs(p['unrealized']) * marginal_rate
            result += f"  {p['ticker']}: {p['shares']} shares | Cost ${p['cost_basis']:.2f} -> Current ${p['current_price']:.2f} | Loss ${p['unrealized']:,.2f} ({p['holding_period']}) | Est. Tax Saving: ${tax_saving:,.2f}\n"

        if not (losses_st or losses_lt):
            result += "  No positions with unrealized losses found.\n"

        result += f"""
SUMMARY:
- Short-Term Losses Available: ${st_loss_total:,.2f}
- Long-Term Losses Available: ${lt_loss_total:,.2f}
- Total Harvestable Losses: ${total_harvestable:,.2f}
- Estimated Tax Savings at {marginal_rate:.0%}: ${total_harvestable * marginal_rate:,.2f}

OFFSET POTENTIAL:
- Short-Term Gains to Offset: ${st_gain_total:,.2f}
- Long-Term Gains to Offset: ${lt_gain_total:,.2f}
- Net Gain After Harvesting: ${(st_gain_total + lt_gain_total) - total_harvestable:,.2f}
- Remaining Loss Deduction (max $3,000/yr ordinary income): {"$3,000" if total_harvestable > (st_gain_total + lt_gain_total) else "N/A"}

WASH SALE REMINDER: Avoid repurchasing the same or substantially identical securities within 30 days before or after the sale."""
        return result
    except Exception as e:
        return f"Error analyzing harvesting opportunities: {str(e)}"


@tool
def calculate_tax_impact(client_id: str, action_type: str, amount: str):
    """Estimate the tax impact of a proposed trade or financial action.

    Args:
        client_id: The client ID
        action_type: Type of action - 'sell_stock', 'roth_conversion', 'charitable_donation', 'capital_gain', 'exercise_options'
        amount: Dollar amount of the action
    """
    try:
        profile = get_client_tax_data(client_id)
        if not profile:
            return f"Client {client_id} not found."

        amount_val = float(str(amount).replace('$', '').replace(',', ''))
        marginal = profile.get('marginal_rate', 0.24)
        state_rate = profile.get('state_rate', 0.0)
        combined = marginal + state_rate
        agi = profile.get('estimated_agi', 0)
        niit_threshold = 250000 if 'Joint' in profile.get('filing_status', '') else 200000
        niit_rate = 0.038 if agi > niit_threshold else 0.0

        result = f"""Tax Impact Analysis - {action_type.replace('_', ' ').title()}:
Client: {profile.get('name', client_id)}
Amount: ${amount_val:,.2f}
"""
        if action_type == 'sell_stock':
            st_tax = amount_val * (marginal + state_rate + niit_rate)
            lt_tax = amount_val * (0.15 + state_rate + niit_rate)
            result += f"""
If Short-Term Gain:
  Federal Tax ({marginal:.0%}): ${amount_val * marginal:,.2f}
  State Tax ({state_rate:.1%}): ${amount_val * state_rate:,.2f}
  NIIT ({niit_rate:.1%}): ${amount_val * niit_rate:,.2f}
  Total Tax: ${st_tax:,.2f}
  Net After Tax: ${amount_val - st_tax:,.2f}

If Long-Term Gain:
  Federal Tax (15%): ${amount_val * 0.15:,.2f}
  State Tax ({state_rate:.1%}): ${amount_val * state_rate:,.2f}
  NIIT ({niit_rate:.1%}): ${amount_val * niit_rate:,.2f}
  Total Tax: ${lt_tax:,.2f}
  Net After Tax: ${amount_val - lt_tax:,.2f}

Long-term holding saves: ${st_tax - lt_tax:,.2f}"""

        elif action_type == 'roth_conversion':
            federal_tax = amount_val * marginal
            state_tax = amount_val * state_rate
            total_tax = federal_tax + state_tax
            result += f"""
Conversion treated as ordinary income:
  Federal Tax ({marginal:.0%}): ${federal_tax:,.2f}
  State Tax ({state_rate:.1%}): ${state_tax:,.2f}
  Total Tax Due: ${total_tax:,.2f}

New Estimated AGI: ${agi + amount_val:,.2f}
Bracket Impact: {"May push into higher bracket" if agi + amount_val > 501050 else "Stays in current bracket"}

Note: Tax-free growth and withdrawals in retirement may offset the upfront cost."""

        elif action_type == 'charitable_donation':
            federal_saving = amount_val * marginal
            state_saving = amount_val * state_rate
            total_saving = federal_saving + state_saving
            result += f"""
Itemized Deduction Impact:
  Federal Tax Saving ({marginal:.0%}): ${federal_saving:,.2f}
  State Tax Saving ({state_rate:.1%}): ${state_saving:,.2f}
  Total Tax Benefit: ${total_saving:,.2f}
  Effective Cost of Donation: ${amount_val - total_saving:,.2f}

Tip: Donating appreciated securities avoids capital gains tax entirely.
AGI Limitation: Charitable deductions capped at 60% of AGI for cash (${agi * 0.6:,.0f})."""

        elif action_type == 'capital_gain':
            lt_rate = 0.20 if agi > 583750 else (0.15 if agi > 94050 else 0.0)
            federal_tax = amount_val * lt_rate
            state_tax = amount_val * state_rate
            niit_tax = amount_val * niit_rate
            total = federal_tax + state_tax + niit_tax
            result += f"""
Long-Term Capital Gains Tax:
  Federal LTCG Rate: {lt_rate:.0%}
  Federal Tax: ${federal_tax:,.2f}
  State Tax ({state_rate:.1%}): ${state_tax:,.2f}
  NIIT ({niit_rate:.1%}): ${niit_tax:,.2f}
  Total Tax: ${total:,.2f}
  Net Proceeds: ${amount_val - total:,.2f}"""

        elif action_type == 'exercise_options':
            federal_tax = amount_val * marginal
            state_tax = amount_val * state_rate
            fica = min(amount_val, max(0, 168600 - agi)) * 0.0765
            total = federal_tax + state_tax + fica
            result += f"""
Stock Option Exercise (NSO - spread taxed as ordinary income):
  Federal Tax ({marginal:.0%}): ${federal_tax:,.2f}
  State Tax ({state_rate:.1%}): ${state_tax:,.2f}
  FICA (if applicable): ${fica:,.2f}
  Total Tax: ${total:,.2f}

For ISOs: No tax at exercise, but spread may trigger AMT.
Consult your tax advisor for ISO-specific analysis."""

        else:
            result += f"""
Estimated tax at combined rate ({combined:.1%}):
  Federal: ${amount_val * marginal:,.2f}
  State: ${amount_val * state_rate:,.2f}
  Total: ${amount_val * combined:,.2f}"""

        return result
    except Exception as e:
        return f"Error calculating tax impact: {str(e)}"


@tool
def get_capital_gains_summary(client_id: str, tax_year: str = None):
    """Get a summary of realized and unrealized capital gains for the client.

    Args:
        client_id: The client ID
        tax_year: Tax year (defaults to current year)
    """
    try:
        positions = get_client_positions(client_id)
        profile = get_client_tax_data(client_id)
        if not positions:
            return f"No portfolio data found for {client_id}."

        year = tax_year or str(datetime.now().year)

        st_gains = sum(p.get('unrealized_gain', 0) for p in positions if p.get('holding_period') == 'short_term' and p.get('unrealized_gain', 0) > 0)
        st_losses = sum(p.get('unrealized_gain', 0) for p in positions if p.get('holding_period') == 'short_term' and p.get('unrealized_gain', 0) < 0)
        lt_gains = sum(p.get('unrealized_gain', 0) for p in positions if p.get('holding_period') == 'long_term' and p.get('unrealized_gain', 0) > 0)
        lt_losses = sum(p.get('unrealized_gain', 0) for p in positions if p.get('holding_period') == 'long_term' and p.get('unrealized_gain', 0) < 0)
        net = st_gains + st_losses + lt_gains + lt_losses

        marginal = profile.get('marginal_rate', 0.24) if profile else 0.24
        state_rate = profile.get('state_rate', 0.0) if profile else 0.0

        result = f"""Capital Gains Summary for {client_id} - Tax Year {year}:

UNREALIZED GAINS & LOSSES (Current Portfolio):

Short-Term (held < 1 year):
  Gains: ${st_gains:,.2f}
  Losses: ${st_losses:,.2f}
  Net Short-Term: ${st_gains + st_losses:,.2f}

Long-Term (held >= 1 year):
  Gains: ${lt_gains:,.2f}
  Losses: ${lt_losses:,.2f}
  Net Long-Term: ${lt_gains + lt_losses:,.2f}

TOTAL:
  Net Unrealized: ${net:,.2f}

ESTIMATED TAX LIABILITY IF ALL REALIZED:
  Short-Term (taxed as ordinary @ {marginal:.0%}): ${max(0, st_gains + st_losses) * marginal:,.2f}
  Long-Term (taxed at 15%): ${max(0, lt_gains + lt_losses) * 0.15:,.2f}
  State Tax ({state_rate:.1%}): ${max(0, net) * state_rate:,.2f}
  Total Estimated Tax: ${max(0, st_gains + st_losses) * marginal + max(0, lt_gains + lt_losses) * 0.15 + max(0, net) * state_rate:,.2f}

POSITIONS BY HOLDING PERIOD:
"""
        for p in sorted(positions, key=lambda x: x.get('unrealized_gain', 0)):
            gain = p.get('unrealized_gain', 0)
            marker = "LOSS" if gain < 0 else "GAIN"
            result += f"  {p['ticker']:6s} | {p.get('holding_period', '?'):10s} | ${gain:>10,.2f} [{marker}]\n"

        return result
    except Exception as e:
        return f"Error generating capital gains summary: {str(e)}"


@tool
def recommend_tax_strategy(client_id: str, goal: str = None):
    """Generate a personalized tax optimization strategy for the client.

    Args:
        client_id: The client ID
        goal: Optional goal - 'minimize_taxes', 'maximize_deductions', 'retirement_optimization', 'year_end_planning', 'charitable_giving'
    """
    try:
        profile = get_client_tax_data(client_id)
        positions = get_client_positions(client_id)
        if not profile:
            return f"Client {client_id} not found."

        goal = goal or "minimize_taxes"
        agi = profile.get('estimated_agi', 0)
        bracket = profile.get('tax_bracket', '24%')
        filing = profile.get('filing_status', 'Single')
        state = profile.get('state', 'Unknown')
        retirement = profile.get('retirement_contributions', {})
        deductions = profile.get('deductions', {})

        harvestable = sum(abs(p.get('unrealized_gain', 0)) for p in (positions or []) if p.get('unrealized_gain', 0) < 0)

        strategies = []

        # Tax-loss harvesting
        if harvestable > 0:
            strategies.append(
                f"1. TAX-LOSS HARVESTING: ${harvestable:,.0f} in harvestable losses available. "
                f"Estimated tax saving: ${harvestable * profile.get('marginal_rate', 0.24):,.0f}. "
                f"Replace sold positions with similar (non-identical) ETFs to maintain exposure."
            )

        # Retirement contributions
        max_401k = 23500
        max_ira = 7000
        max_hsa = 8300 if 'Joint' in filing else 4150
        remaining_401k = max(0, max_401k - retirement.get('401k', 0))
        remaining_ira = max(0, max_ira - retirement.get('ira', 0))
        remaining_hsa = max(0, max_hsa - retirement.get('hsa', 0))
        total_remaining = remaining_401k + remaining_ira + remaining_hsa

        if total_remaining > 0:
            strategies.append(
                f"2. MAXIMIZE RETIREMENT CONTRIBUTIONS: ${total_remaining:,.0f} in contribution room remaining. "
                f"401(k): ${remaining_401k:,.0f} | IRA: ${remaining_ira:,.0f} | HSA: ${remaining_hsa:,.0f}. "
                f"Each dollar reduces taxable income at your {bracket} marginal rate."
            )

        # Roth conversion
        if goal in ('retirement_optimization', 'minimize_taxes'):
            strategies.append(
                f"3. ROTH CONVERSION LADDER: Consider converting up to the top of the {bracket} bracket "
                f"to lock in current rates. Future tax-free growth and no RMDs offset upfront cost."
            )

        # Charitable strategies
        if agi > 200000:
            strategies.append(
                f"4. CHARITABLE GIVING: Donate appreciated long-term securities directly to avoid capital gains. "
                f"Current charitable deductions: ${deductions.get('charitable', 0):,.0f}. "
                f"Consider a Donor-Advised Fund (DAF) for bunching multiple years of giving."
            )

        # State-specific
        if state in ('CA', 'NY', 'NJ', 'CT'):
            strategies.append(
                f"5. STATE TAX OPTIMIZATION ({state}): High-state-tax state. "
                f"Consider municipal bonds for tax-free income. "
                f"SALT deduction capped at $10,000 - explore workarounds like entity-level taxes if applicable."
            )
        elif state == 'TX':
            strategies.append(
                f"5. STATE TAX ADVANTAGE ({state}): No state income tax. "
                f"Focus federal optimization; consider realizing gains in current state before any relocation."
            )

        # Year-end
        if goal == 'year_end_planning' or datetime.now().month >= 10:
            strategies.append(
                f"6. YEAR-END PLANNING: Review estimated payments, accelerate/defer income where possible, "
                f"and ensure all harvesting is complete before Dec 31. "
                f"Check for AMT exposure with your accountant."
            )

        # Bracket management
        strategies.append(
            f"{'7' if len(strategies) >= 6 else str(len(strategies) + 1)}. BRACKET MANAGEMENT: "
            f"Current AGI ${agi:,.0f} in the {bracket} bracket. "
            f"Strategic timing of income recognition and deductions can keep you in a lower bracket."
        )

        result = f"""Personalized Tax Strategy for {profile.get('name', client_id)}:
Goal: {goal.replace('_', ' ').title()}
Filing: {filing} | Bracket: {bracket} | State: {state}
Estimated AGI: ${agi:,.0f}

RECOMMENDED STRATEGIES:
"""
        for s in strategies:
            result += f"\n{s}\n"

        result += f"""
ESTIMATED TOTAL TAX SAVINGS: ${harvestable * profile.get('marginal_rate', 0.24) + total_remaining * profile.get('marginal_rate', 0.24):,.0f}

DISCLAIMER: This analysis is for informational purposes. Consult a qualified tax professional (CPA or EA) before executing any tax strategy."""
        return result
    except Exception as e:
        return f"Error generating tax strategy: {str(e)}"


@tool
def get_memory_context(client_id: str, session_id: str = None):
    """Get conversation context from AgentCore Memory."""
    try:
        if not memory_id:
            initialize_memory(client_id, session_id)
        context = get_conversation_context(client_id, session_id or "default")
        if context:
            return f"Previous Conversation Context:\n{context}"
        return "No previous conversation history found."
    except Exception as e:
        logger.error(f"Error getting memory context: {e}")
        return "Unable to retrieve conversation history at this time."


@tool
def save_conversation_memory(client_id: str, user_message: str, agent_response: str, session_id: str = None):
    """Save current conversation to AgentCore Memory."""
    try:
        if not memory_id:
            initialize_memory(client_id, session_id)
        save_conversation_to_memory(client_id, session_id or "default", user_message, agent_response)
        return "Conversation saved to memory successfully."
    except Exception as e:
        logger.error(f"Error saving to memory: {e}")
        return "Unable to save conversation to memory."

# =============================================================================
# CrewAI INTEGRATION
# =============================================================================

def run_crewai_analysis(client_id: str, query: str):
    """Run a CrewAI crew for deep tax analysis when available."""
    if not CREWAI_AVAILABLE:
        return None

    try:
        tax_specialist = CrewAgent(
            role="Tax Strategy Specialist",
            goal="Analyze the client's tax situation and provide actionable, legally compliant tax optimization strategies",
            backstory=(
                "You are a senior tax strategist with 20 years of experience at a top wealth "
                "management firm. You hold CPA and CFP designations. You specialize in high-net-worth "
                "tax planning, capital gains optimization, and multi-year tax projection. "
                "You always consider wash sale rules, AMT implications, and state-specific tax laws."
            ),
            verbose=True,
            allow_delegation=False,
        )

        tax_analysis_task = CrewTask(
            description=(
                f"Analyze the tax situation for client {client_id}. "
                f"Client query: {query}. "
                "Review their tax bracket, filing status, current deductions, and portfolio positions. "
                "Identify immediate tax-saving opportunities."
            ),
            expected_output="A structured tax situation analysis with key findings and risk areas.",
            agent=tax_specialist,
        )

        harvesting_task = CrewTask(
            description=(
                f"For client {client_id}, identify all tax-loss harvesting opportunities. "
                "List positions with unrealized losses, calculate potential tax savings, "
                "and suggest replacement securities that avoid wash sale violations."
            ),
            expected_output="A list of harvesting opportunities with estimated savings and replacement suggestions.",
            agent=tax_specialist,
        )

        strategy_task = CrewTask(
            description=(
                f"Create a comprehensive year-end tax strategy for client {client_id}. "
                "Incorporate the analysis and harvesting findings. "
                "Include: bracket management, retirement contribution optimization, "
                "charitable giving strategies, and Roth conversion analysis. "
                "Provide a prioritized action plan with deadlines."
            ),
            expected_output="A prioritized tax optimization action plan with estimated savings per strategy.",
            agent=tax_specialist,
        )

        crew = Crew(
            agents=[tax_specialist],
            tasks=[tax_analysis_task, harvesting_task, strategy_task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()
        return str(result)
    except Exception as e:
        logger.error(f"CrewAI analysis failed: {e}")
        return None

# =============================================================================
# CROSS-AGENT ORCHESTRATION
# =============================================================================

try:
    from cross_agent import invoke_peer_agent, get_available_agents
    CROSS_AGENT_AVAILABLE = True
except ImportError:
    CROSS_AGENT_AVAILABLE = False

@tool
def consult_financial_planner(query: str, client_id: str = ""):
    """Consult Sophia (Financial Planner) for portfolio details, allocation strategy, or retirement projections.

    Args:
        query: The financial planning question to ask Sophia
        client_id: The client ID for context

    Returns:
        Sophia's financial planning analysis
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('sophia', query, client_id)

@tool
def consult_market_analyst(query: str, client_id: str = ""):
    """Consult Marcus (Market Analyst) for current market conditions, stock analysis, or sector trends.

    Args:
        query: The market-related question to ask Marcus
        client_id: The client ID for context

    Returns:
        Marcus's market analysis
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('marcus', query, client_id)


# =============================================================================
# STRANDS AGENT SETUP
# =============================================================================

model = BedrockModel(model_id=MODEL_ID)

base_tools = [
    get_client_tax_profile,
    find_harvesting_opportunities,
    calculate_tax_impact,
    get_capital_gains_summary,
    recommend_tax_strategy,
    get_memory_context,
    save_conversation_memory,
    consult_financial_planner,
    consult_market_analyst,
]

agent = Agent(
    model=model,
    tools=base_tools,
    system_prompt="""You are Olivia, a senior tax optimization specialist at WealthAI Advisors.

CRITICAL: You MUST use your tools to provide accurate information. Never guess or fabricate tax data.

YOUR TOOLS:
- get_client_tax_profile(client_id): Look up client tax bracket, filing status, deductions, retirement contributions
- find_harvesting_opportunities(client_id): Scan portfolio for tax-loss harvesting positions
- calculate_tax_impact(client_id, action_type, amount): Estimate tax impact of trades or financial actions
- get_capital_gains_summary(client_id, tax_year=None): Get full capital gains breakdown
- recommend_tax_strategy(client_id, goal=None): Generate personalized tax optimization strategy
- get_memory_context(client_id, session_id=None): Retrieve conversation history
- save_conversation_memory(client_id, user_message, agent_response, session_id=None): Save conversation context
- consult_financial_planner(query, client_id): Ask Sophia for portfolio details or allocation info
- consult_market_analyst(query, client_id): Ask Marcus for current market data and stock analysis

CROSS-AGENT COLLABORATION:
- When you need portfolio details to assess tax impact → consult_financial_planner
- When you need current market prices for harvesting analysis → consult_market_analyst

MANDATORY TOOL USAGE:
1. When a client asks about their tax situation -> ALWAYS use get_client_tax_profile FIRST
2. When asked about harvesting or losses -> ALWAYS use find_harvesting_opportunities
3. When asked about selling stock or making financial moves -> ALWAYS use calculate_tax_impact
4. When asked for a strategy or plan -> ALWAYS use recommend_tax_strategy
5. When asked about gains/losses summary -> ALWAYS use get_capital_gains_summary

RESPONSE GUIDELINES:
- Always disclose that you provide informational analysis, not tax advice
- Reference specific IRS rules when relevant (wash sale rule, Section 1031, etc.)
- Consider both federal and state tax implications
- Flag any potential AMT exposure
- Remind clients of key deadlines (estimated payments, year-end harvesting, contribution limits)
- When discussing charitable giving, mention the advantage of donating appreciated securities
- Always consider the client's full tax picture, not just one position

TAX YEAR CONTEXT: Current tax year is 2026. Key limits:
- 401(k): $23,500 (under 50) / $31,000 (50+)
- IRA: $7,000 (under 50) / $8,000 (50+)
- HSA: $4,300 individual / $8,550 family
- SALT deduction cap: $10,000
- Standard deduction: $15,000 (single) / $30,000 (MFJ)

Be professional, precise, and thorough. Use clear formatting with dollar amounts and percentages. Always provide the "why" behind each recommendation.""",
)

# =============================================================================
# AGENTCORE ENTRYPOINT
# =============================================================================

@app.entrypoint
def tax_optimizer_agent(payload, context):
    """Olivia Tax Optimizer Agent with CrewAI deep analysis and Strands tools."""
    request_start = time.time()
    try:
        user_input = payload.get("prompt", "Hello! How can I help with your taxes?")
        client_id = payload.get("customer_id", "")
        session_id = context.session_id or ""

        logger.info(f"Olivia Agent - Processing request for client: {client_id}")
        logger.info(f"Session ID: {session_id}")

        current_agent = agent

        if client_id or session_id:
            initialize_memory(client_id, session_id)

            if MEMORY_TOOLS_AVAILABLE and client_id:
                provider = initialize_memory_tools(client_id, session_id)
                if provider and hasattr(provider, 'tools'):
                    try:
                        enhanced_tools = base_tools + provider.tools
                        current_agent = Agent(model=model, tools=enhanced_tools)
                        logger.info(f"Enhanced agent with {len(provider.tools)} memory tools")
                    except Exception as e:
                        logger.warning(f"Could not enhance agent: {e}")

        # Retrieve conversation context
        conv_context = ""
        if client_id:
            try:
                ctx_start = time.time()
                conv_context = get_conversation_context(client_id, session_id)
                ctx_ms = (time.time() - ctx_start) * 1000
                if conv_context:
                    if metrics:
                        metrics.track_memory(hit=True, retrieval_ms=ctx_ms)
                elif metrics:
                    metrics.track_memory(hit=False, retrieval_ms=ctx_ms)
            except Exception as e:
                logger.warning(f"Could not retrieve context: {e}")
                if metrics:
                    metrics.track_memory(hit=False)

        # Build enhanced input
        enhanced_input = user_input
        if client_id:
            enhanced_input = f"Client ID: {client_id}\n\n{user_input}"
        if conv_context:
            enhanced_input = f"Previous conversation context:\n{conv_context}\n\nCurrent request: {enhanced_input}"

        # Optionally run CrewAI for deep analysis requests
        deep_keywords = ["comprehensive", "full analysis", "year-end plan", "deep dive", "complete review"]
        crewai_result = None
        if CREWAI_AVAILABLE and any(kw in user_input.lower() for kw in deep_keywords):
            logger.info("Running CrewAI deep tax analysis...")
            crewai_result = run_crewai_analysis(client_id, user_input)
            if crewai_result:
                enhanced_input += f"\n\nDeep Analysis (from tax specialist crew):\n{crewai_result[:4000]}"

        response = current_agent(enhanced_input)

        # Parse response
        try:
            if hasattr(response, 'message') and response.message:
                if isinstance(response.message, dict) and 'content' in response.message:
                    content = response.message['content']
                    if isinstance(content, list) and len(content) > 0:
                        first = content[0]
                        result = first.get('text', str(first)) if isinstance(first, dict) else str(first)
                    elif isinstance(content, str):
                        result = content
                    else:
                        result = str(content)
                else:
                    result = str(response.message)
            elif hasattr(response, 'content'):
                result = response.content
            elif hasattr(response, 'text'):
                result = response.text
            elif isinstance(response, dict):
                result = response.get('text') or response.get('content') or response.get('message') or str(response)
            elif isinstance(response, str):
                result = response
            else:
                result = str(response)
        except (KeyError, IndexError, AttributeError) as e:
            logger.error(f"Error parsing response: {e}")
            result = "I apologize, but I encountered a response processing error. Please try again."

        # Save to memory
        if client_id:
            try:
                save_conversation_to_memory(client_id, session_id or "default", user_input, result)
            except Exception as e:
                logger.warning(f"Could not save to memory: {e}")

        # Emit end-to-end agent response metrics
        if metrics:
            request_latency = (time.time() - request_start) * 1000
            input_token_est = len(enhanced_input) // 4
            output_token_est = len(result) // 4
            metrics.emit_agent_response(
                latency_ms=request_latency,
                input_tokens=input_token_est,
                output_tokens=output_token_est,
                client_id=client_id,
                session_id=session_id
            )

        return result
    except Exception as e:
        logger.error(f"Error in Olivia agent: {e}")
        if metrics:
            request_latency = (time.time() - request_start) * 1000
            metrics.emit_agent_response(latency_ms=request_latency, input_tokens=0, output_tokens=0)
        return f"I apologize, but I encountered an error: {str(e)}. Please try again or contact support."


if __name__ == "__main__":
    app.run()
