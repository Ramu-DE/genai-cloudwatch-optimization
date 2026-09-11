#!/usr/bin/env python3
"""
Marcus Market Analyst Agent - Complete Implementation with Memory & Session Management
Integrates all DynamoDB, memory, and session logic as Strands tools
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
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
    from metrics_emitter import MetricsEmitter
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

# Configure logging
log_file = os.path.join(os.path.expanduser('~'), 'marcus_agent.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger.info("📈 MARCUS MARKET ANALYST AGENT STARTING UP")
logger.info(f"Python version: {sys.version}")
logger.info(f"AWS Region: {os.environ.get('AWS_REGION', 'us-west-2')}")

# AgentCore Memory Integration
try:
    from bedrock_agentcore.memory import MemoryClient
    from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider
    MEMORY_AVAILABLE = True
    MEMORY_TOOLS_AVAILABLE = True
    logger.info("✅ AgentCore Memory and Tools available")
except ImportError:
    try:
        from bedrock_agentcore.memory import MemoryClient
        MEMORY_AVAILABLE = True
        MEMORY_TOOLS_AVAILABLE = False
        logger.info("✅ AgentCore Memory available (no tools)")
    except ImportError:
        MEMORY_AVAILABLE = False
        MEMORY_TOOLS_AVAILABLE = False
        logger.warning("⚠️ AgentCore Memory not available")

# Initialize AgentCore App
app = BedrockAgentCoreApp()

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-west-2')
MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0')

# Initialize metrics emitter
metrics = MetricsEmitter(agent_name='marcus', model_id=MODEL_ID) if METRICS_AVAILABLE else None

# DynamoDB setup
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)

# DynamoDB table names
TABLES = {
    'clients': 'wealth_mgmt_client_profiles',
    'portfolios': 'wealth_mgmt_portfolios',
    'transactions': 'wealth_mgmt_transactions',
    'market_data': 'wealth_mgmt_market_data',
    'user_auth': 'wealth_mgmt_user_auth'
}

# Global memory client and memory ID
memory_client = None
memory_id = None
memory_tool_provider = None

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def decimal_to_native(obj):
    """Convert Decimal objects to native Python types"""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_native(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_native(v) for v in obj]
    return obj

def log_dynamodb_request(operation: str, table_name: str, key: dict = None, item: dict = None):
    """Log DynamoDB request with full details"""
    logger.info("=" * 80)
    logger.info("🗄️ DYNAMODB REQUEST START")
    logger.info("=" * 80)
    logger.info(f"📊 Operation: {operation}")
    logger.info(f"📋 Table: {table_name}")
    logger.info(f"🔑 Key: {json.dumps(key, default=str) if key else 'None'}")
    logger.info(f"📦 Item: {json.dumps(item, default=str) if item else 'None'}")
    logger.info(f"⏰ Timestamp: {datetime.now().isoformat()}")

def log_dynamodb_response(operation: str, response: dict, duration: float):
    """Log DynamoDB response with full details"""
    logger.info("-" * 80)
    logger.info("📥 DYNAMODB RESPONSE")
    logger.info("-" * 80)
    logger.info(f"📊 Operation: {operation}")
    logger.info(f"⏱️ Duration: {duration:.3f} seconds")
    logger.info(f"📊 HTTP Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode', 'Unknown')}")
    logger.info(f"📋 Items Count: {len(response.get('Items', []))}")
    logger.info(f"📦 Response Size: {len(str(response))} characters")
    logger.info("=" * 80)
    logger.info("✅ DYNAMODB REQUEST COMPLETE")
    logger.info("=" * 80)

# ============================================================================
# MEMORY MANAGEMENT FUNCTIONS
# ============================================================================

def initialize_memory(client_id=None, session_id=None):
    """Initialize AgentCore Memory with a single unified memory object"""
    global memory_client, memory_id

    if not MEMORY_AVAILABLE:
        logger.warning("⚠️ AgentCore Memory not available - using basic conversation tracking")
        return None

    try:
        target_memory_id = os.getenv('BEDROCK_AGENTCORE_MEMORY_ID', 'wealth_mgmt_marcus_market_analyst_memory')
    except Exception:
        target_memory_id = 'wealth_mgmt_marcus_market_analyst_memory'

    if memory_id:
        logger.info(f"🧠 Using cached unified memory ID: {memory_id}")
        return memory_id

    try:
        logger.info("🧠 Initializing unified AgentCore Memory with long-term strategies...")
        memory_client = MemoryClient(region_name=AWS_REGION)

        try:
            memories = memory_client.list_memories()
            existing_memory = None
            for m in memories:
                memory_id_field = m.get('id')
                if memory_id_field and target_memory_id in memory_id_field:
                    existing_memory = m
                    break

            if existing_memory:
                memory_id = existing_memory.get('id')
                logger.info(f"✅ Found existing unified memory: {memory_id}")
                return memory_id

        except Exception as e:
            logger.warning(f"Error listing memories: {e}")

        try:
            memory = memory_client.create_memory_and_wait(
                name=target_memory_id,
                description="Unified persistent memory for Marcus market analyst agent - stores all client interactions",
                strategies=[
                    {
                        "summaryMemoryStrategy": {
                            "name": "MarketAnalysisSummarizer",
                            "description": "Summarizes market consultations and portfolio reviews across all clients",
                            "namespaces": ["/summaries/marcus/{actorId}/{sessionId}"]
                        }
                    },
                    {
                        "semanticMemoryStrategy": {
                            "name": "MarketKnowledgeBase",
                            "description": "Stores market insights, sector analysis, and investment research",
                            "namespaces": ["/knowledge/marcus/{actorId}/markets"]
                        }
                    },
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": "InvestmentPreferences",
                            "description": "Learns client investment preferences and risk tolerance patterns",
                            "namespaces": ["/preferences/marcus/{actorId}"]
                        }
                    }
                ],
                event_expiry_days=5
            )

            memory_id = memory.get('id') or memory.get('memoryId')
            logger.info(f"✅ Unified memory created: {memory_id}")
            return memory_id

        except Exception as create_error:
            logger.error(f"Failed to create unified memory: {create_error}")

            if "already exists" in str(create_error):
                try:
                    memories = memory_client.list_memories()
                    for m in memories:
                        memory_id_field = m.get('id')
                        if memory_id_field and target_memory_id in memory_id_field:
                            memory_id = memory_id_field
                            logger.info(f"✅ Found existing unified memory: {memory_id}")
                            return memory_id
                except Exception as find_error:
                    logger.error(f"Error in memory search: {find_error}")

            logger.error(f"⚠️ Could not set up unified AgentCore Memory: {create_error}")
            return None

    except Exception as e:
        logger.error(f"⚠️ Could not set up unified AgentCore Memory: {e}")
        memory_id = None
        return None

def initialize_memory_tools(client_id, session_id=None):
    """Initialize AgentCore Memory Tool Provider with unified memory object"""
    global memory_tool_provider, memory_id

    if not MEMORY_TOOLS_AVAILABLE or not memory_id:
        logger.info("⚠️ Memory tools not available or memory not initialized")
        return None

    try:
        namespace = f"/preferences/marcus/{client_id}"

        memory_tool_provider = AgentCoreMemoryToolProvider(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id or "default",
            namespace=namespace,
            region=AWS_REGION
        )

        logger.info("✅ Memory tool provider initialized with unified memory")
        logger.info(f"🗂️ Actor (client_id): {client_id}, Session: {session_id or 'default'}")
        logger.info(f"🗂️ Namespace: {namespace}")
        return memory_tool_provider

    except Exception as e:
        logger.error(f"⚠️ Could not initialize memory tool provider: {e}")
        return None

def save_conversation_to_memory(client_id, session_id, user_message, agent_response):
    """Save conversation turn to unified AgentCore Memory with length management"""
    global memory_client, memory_id

    if not memory_id or not memory_client:
        logger.debug("💾 Memory not available - skipping save")
        return

    try:
        logger.info(f"💾 Saving to unified memory: Client={client_id}, Session={session_id}")

        max_length = 8500
        truncated_user = user_message
        if len(user_message) > max_length:
            truncated_user = user_message[:max_length] + "... [truncated]"

        truncated_response = agent_response
        if len(agent_response) > max_length:
            half = max_length // 2
            truncated_response = agent_response[:half] + "... [middle truncated] ..." + agent_response[-half:]

        memory_client.create_event(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
            messages=[
                (truncated_user, "user"),
                (truncated_response, "assistant")
            ]
        )
        logger.info("✅ Successfully saved to unified memory")

    except Exception as e:
        logger.error(f"⚠️ Could not save to memory: {e}")

def get_conversation_context(client_id, session_id):
    """Get recent conversation context from unified AgentCore Memory"""
    global memory_client, memory_id

    if not memory_id or not memory_client:
        initialize_memory(client_id, session_id)

    if not memory_id or not memory_client:
        return ""

    try:
        session_exists = False
        try:
            events = memory_client.list_events(
                memory_id=memory_id,
                actor_id=client_id,
                session_id=session_id
            )
            session_exists = len(events) > 0
        except Exception:
            session_exists = False

        if not session_exists:
            return ""

        recent_turns = memory_client.get_last_k_turns(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
            k=5
        )

        if recent_turns:
            context_parts = ["Recent conversation history:"]
            for turn in recent_turns:
                role = turn.get('role', 'unknown')
                content = turn.get('content', '')
                if content:
                    prefix = "Client" if role == "user" else "Marcus"
                    context_parts.append(f"{prefix}: {content[:200]}...")
            return "\n".join(context_parts)

        return ""

    except Exception as e:
        logger.error(f"⚠️ Error retrieving conversation context: {e}")
        return ""

# ============================================================================
# DYNAMODB DATA ACCESS FUNCTIONS
# ============================================================================

def get_client_profile_from_db(client_id: str):
    """Get client profile from DynamoDB"""
    table_name = TABLES['clients']
    log_dynamodb_request("GetItem", table_name, key={"client_id": client_id})
    start = time.time()

    try:
        table = dynamodb_resource.Table(table_name)
        response = table.get_item(Key={'client_id': client_id})
        duration = time.time() - start
        log_dynamodb_response("GetItem", response, duration)

        if 'Item' in response:
            return decimal_to_native(response['Item'])
        return None
    except Exception as e:
        logger.error(f"Error fetching client profile: {e}")
        return None

def get_portfolio_from_db(client_id: str, portfolio_type: str = None):
    """Get portfolio holdings from DynamoDB"""
    table_name = TABLES['portfolios']
    log_dynamodb_request("Query", table_name, key={"client_id": client_id})
    start = time.time()

    try:
        table = dynamodb_resource.Table(table_name)
        if portfolio_type:
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('client_id').eq(client_id)
                & boto3.dynamodb.conditions.Key('portfolio_type').eq(portfolio_type)
            )
        else:
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('client_id').eq(client_id)
            )
        duration = time.time() - start
        log_dynamodb_response("Query", response, duration)
        items = response.get('Items', [])
        return [decimal_to_native(item) for item in items] if items else None
    except Exception as e:
        logger.error(f"Error fetching portfolio: {e}")
        return None

def get_transaction_history_from_db(client_id: str, limit: int = 10):
    """Get transaction history from DynamoDB"""
    table_name = TABLES['transactions']
    log_dynamodb_request("Query", table_name, key={"client_id": client_id})
    start = time.time()

    try:
        table = dynamodb_resource.Table(table_name)
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('client_id').eq(client_id),
            ScanIndexForward=False,
            Limit=limit
        )
        duration = time.time() - start
        log_dynamodb_response("Query", response, duration)
        items = response.get('Items', [])
        return [decimal_to_native(item) for item in items] if items else None
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        return None

# ============================================================================
# FALLBACK DATA (empty — client data loaded from DynamoDB / trading platform)
# ============================================================================

SAMPLE_CLIENT_PROFILES = {}

SAMPLE_PORTFOLIOS = {}

SECTOR_DATA = {
    "technology": {
        "sector": "Technology",
        "index": "XLK",
        "performance": {"1D": "+0.85%", "1W": "+2.14%", "1M": "+4.72%", "3M": "+11.38%", "YTD": "+28.65%", "1Y": "+34.21%"},
        "top_holdings": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM"],
        "pe_ratio": 32.4,
        "dividend_yield": 0.68,
        "market_cap_T": 18.2,
        "sentiment": "Bullish",
        "key_drivers": ["AI infrastructure spending acceleration", "Cloud revenue growth", "Enterprise software demand", "Semiconductor cycle recovery"],
        "risks": ["Regulatory scrutiny on AI", "Elevated valuations", "Interest rate sensitivity"]
    },
    "healthcare": {
        "sector": "Healthcare",
        "index": "XLV",
        "performance": {"1D": "+0.32%", "1W": "-0.45%", "1M": "+1.85%", "3M": "+5.62%", "YTD": "+8.14%", "1Y": "+12.37%"},
        "top_holdings": ["UNH", "JNJ", "LLY", "ABBV", "MRK"],
        "pe_ratio": 18.7,
        "dividend_yield": 1.52,
        "market_cap_T": 7.8,
        "sentiment": "Neutral-Bullish",
        "key_drivers": ["GLP-1 drug revenue surge", "Medicare expansion", "Biotech M&A activity", "Aging demographics"],
        "risks": ["Drug pricing legislation", "Patent cliffs", "Clinical trial failures"]
    },
    "energy": {
        "sector": "Energy",
        "index": "XLE",
        "performance": {"1D": "-0.42%", "1W": "-1.23%", "1M": "-2.18%", "3M": "+3.45%", "YTD": "+5.82%", "1Y": "+9.15%"},
        "top_holdings": ["XOM", "CVX", "COP", "SLB", "EOG"],
        "pe_ratio": 12.1,
        "dividend_yield": 3.28,
        "market_cap_T": 3.2,
        "sentiment": "Neutral",
        "key_drivers": ["OPEC+ production decisions", "Natural gas demand growth", "Energy transition investments", "Geopolitical tensions"],
        "risks": ["Oil price volatility", "Renewable energy competition", "ESG divestment pressure"]
    },
    "financials": {
        "sector": "Financials",
        "index": "XLF",
        "performance": {"1D": "+0.55%", "1W": "+1.38%", "1M": "+3.21%", "3M": "+8.74%", "YTD": "+15.42%", "1Y": "+22.18%"},
        "top_holdings": ["BRK.B", "JPM", "V", "MA", "BAC"],
        "pe_ratio": 15.8,
        "dividend_yield": 1.85,
        "market_cap_T": 9.1,
        "sentiment": "Bullish",
        "key_drivers": ["Net interest margin expansion", "Capital markets recovery", "Fintech integration", "Credit quality resilience"],
        "risks": ["Commercial real estate exposure", "Regulatory capital requirements", "Recession risk"]
    },
    "consumer_discretionary": {
        "sector": "Consumer Discretionary",
        "index": "XLY",
        "performance": {"1D": "+0.28%", "1W": "+0.92%", "1M": "+2.45%", "3M": "+7.18%", "YTD": "+12.85%", "1Y": "+18.94%"},
        "top_holdings": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
        "pe_ratio": 26.3,
        "dividend_yield": 0.92,
        "market_cap_T": 8.4,
        "sentiment": "Neutral-Bullish",
        "key_drivers": ["Consumer spending resilience", "E-commerce growth", "Travel recovery", "Housing market stabilization"],
        "risks": ["Consumer credit tightening", "Inflation persistence", "Discretionary spending pullback"]
    },
    "real_estate": {
        "sector": "Real Estate",
        "index": "XLRE",
        "performance": {"1D": "+0.18%", "1W": "-0.35%", "1M": "+1.42%", "3M": "+4.28%", "YTD": "+6.95%", "1Y": "+10.52%"},
        "top_holdings": ["PLD", "AMT", "EQIX", "SPG", "O"],
        "pe_ratio": 38.2,
        "dividend_yield": 3.45,
        "market_cap_T": 1.4,
        "sentiment": "Neutral",
        "key_drivers": ["Rate cut expectations", "Data center REIT demand", "Industrial logistics growth", "Residential supply shortage"],
        "risks": ["Higher-for-longer rates", "Office vacancy rates", "Commercial loan maturities"]
    }
}

ECONOMIC_INDICATORS = {
    "last_updated": "2026-09-10",
    "indicators": {
        "Federal Funds Rate": {"value": "4.75-5.00%", "previous": "5.00-5.25%", "trend": "Decreasing", "next_meeting": "2026-10-29"},
        "CPI (YoY)": {"value": "2.8%", "previous": "3.0%", "trend": "Decreasing", "released": "2026-09-10"},
        "Core CPI (YoY)": {"value": "3.1%", "previous": "3.3%", "trend": "Decreasing", "released": "2026-09-10"},
        "GDP Growth (Q2 2026)": {"value": "2.4%", "previous": "2.1% (Q1)", "trend": "Increasing", "released": "2026-08-29"},
        "Unemployment Rate": {"value": "3.9%", "previous": "3.8%", "trend": "Stable", "released": "2026-09-06"},
        "10-Year Treasury Yield": {"value": "4.12%", "previous": "4.25%", "trend": "Decreasing", "as_of": "2026-09-10"},
        "S&P 500": {"value": "5,842.30", "previous_close": "5,815.60", "trend": "Increasing", "ytd_return": "+16.8%"},
        "VIX (Volatility Index)": {"value": "14.2", "previous": "15.8", "trend": "Decreasing", "interpretation": "Low volatility - market calm"},
        "US Dollar Index (DXY)": {"value": "103.45", "previous": "104.20", "trend": "Decreasing", "interpretation": "Dollar weakening"},
        "Consumer Confidence": {"value": "108.7", "previous": "106.1", "trend": "Increasing", "released": "2026-08-27"},
        "ISM Manufacturing PMI": {"value": "49.8", "previous": "48.5", "trend": "Increasing", "interpretation": "Near expansion territory"},
        "Nonfarm Payrolls": {"value": "+187K", "previous": "+223K", "trend": "Moderating", "released": "2026-09-06"}
    },
    "market_summary": "The US economy shows resilient growth with moderating inflation. The Fed has begun its easing cycle with a 25bp cut. Labor market remains solid but cooling. Equity markets are near all-time highs driven by AI/tech. Bond yields declining on rate cut expectations."
}

STOCK_ANALYSIS_DATA = {
    "AAPL": {"name": "Apple Inc.", "price": 215.30, "change_1d": "+1.24%", "pe": 29.8, "forward_pe": 27.2, "market_cap": "3.35T", "52w_high": 232.50, "52w_low": 168.40, "dividend_yield": "0.52%", "analyst_rating": "Overweight", "price_target": 240.00, "sector": "Technology", "beta": 1.18, "revenue_growth": "8.2%", "eps_growth": "12.4%", "summary": "Strong iPhone 16 cycle and expanding services revenue. AI features driving upgrade demand. Wearables growth moderating."},
    "MSFT": {"name": "Microsoft Corp.", "price": 442.80, "change_1d": "+0.95%", "pe": 35.2, "forward_pe": 30.8, "market_cap": "3.29T", "52w_high": 468.50, "52w_low": 362.20, "dividend_yield": "0.72%", "analyst_rating": "Strong Buy", "price_target": 500.00, "sector": "Technology", "beta": 0.92, "revenue_growth": "15.8%", "eps_growth": "18.2%", "summary": "Azure cloud growth accelerating with AI workloads. Copilot monetization ramping. LinkedIn and gaming segments stable."},
    "AMZN": {"name": "Amazon.com Inc.", "price": 198.75, "change_1d": "+1.82%", "pe": 42.5, "forward_pe": 32.1, "market_cap": "2.06T", "52w_high": 215.80, "52w_low": 151.30, "dividend_yield": "0%", "analyst_rating": "Strong Buy", "price_target": 230.00, "sector": "Consumer Discretionary", "beta": 1.15, "revenue_growth": "12.5%", "eps_growth": "42.8%", "summary": "AWS revenue reaccelerating. E-commerce margin expansion continuing. Advertising segment growing 25%+ YoY."},
    "NVDA": {"name": "NVIDIA Corp.", "price": 875.50, "change_1d": "+2.35%", "pe": 58.2, "forward_pe": 35.4, "market_cap": "2.15T", "52w_high": 945.00, "52w_low": 480.20, "dividend_yield": "0.03%", "analyst_rating": "Strong Buy", "price_target": 1000.00, "sector": "Technology", "beta": 1.65, "revenue_growth": "122.4%", "eps_growth": "168.5%", "summary": "Dominant AI chip supplier. Blackwell GPU demand exceeding supply. Data center revenue driving >80% of total. Gaming stable."},
    "GOOGL": {"name": "Alphabet Inc.", "price": 176.20, "change_1d": "+0.68%", "pe": 24.8, "forward_pe": 21.5, "market_cap": "2.17T", "52w_high": 192.40, "52w_low": 138.50, "dividend_yield": "0.48%", "analyst_rating": "Buy", "price_target": 200.00, "sector": "Technology", "beta": 1.08, "revenue_growth": "14.2%", "eps_growth": "28.6%", "summary": "Search advertising resilient despite AI disruption fears. Cloud segment turning profitable. YouTube ad revenue growing double-digits."},
    "TSLA": {"name": "Tesla Inc.", "price": 285.60, "change_1d": "-0.72%", "pe": 68.5, "forward_pe": 45.2, "market_cap": "908B", "52w_high": 342.80, "52w_low": 182.50, "dividend_yield": "0%", "analyst_rating": "Hold", "price_target": 280.00, "sector": "Consumer Discretionary", "beta": 2.05, "revenue_growth": "8.5%", "eps_growth": "-12.4%", "summary": "EV market share stable but pricing pressure. FSD progress encouraging. Energy storage business growing rapidly. Margin compression concern."},
    "META": {"name": "Meta Platforms Inc.", "price": 515.40, "change_1d": "+1.15%", "pe": 26.8, "forward_pe": 22.4, "market_cap": "1.31T", "52w_high": 542.80, "52w_low": 390.20, "dividend_yield": "0.38%", "analyst_rating": "Buy", "price_target": 570.00, "sector": "Technology", "beta": 1.22, "revenue_growth": "22.1%", "eps_growth": "35.8%", "summary": "Ad revenue resilient with Reels monetization improving. Metaverse losses narrowing. AI investments driving engagement growth."},
    "JPM": {"name": "JPMorgan Chase & Co.", "price": 218.40, "change_1d": "+0.48%", "pe": 12.5, "forward_pe": 11.8, "market_cap": "627B", "52w_high": 228.50, "52w_low": 172.30, "dividend_yield": "2.18%", "analyst_rating": "Overweight", "price_target": 235.00, "sector": "Financials", "beta": 1.12, "revenue_growth": "9.8%", "eps_growth": "14.2%", "summary": "Best-in-class bank. NII benefiting from rate environment. Investment banking fees recovering. Strong credit quality."},
    "BND": {"name": "Vanguard Total Bond Market ETF", "price": 73.80, "change_1d": "+0.12%", "pe": "N/A", "forward_pe": "N/A", "market_cap": "112B (AUM)", "52w_high": 75.20, "52w_low": 69.80, "dividend_yield": "3.85%", "analyst_rating": "N/A", "price_target": "N/A", "sector": "Fixed Income", "beta": 0.05, "revenue_growth": "N/A", "eps_growth": "N/A", "summary": "Broad US bond market exposure. Duration ~6.5 years. Benefits from rate cuts. Core fixed income allocation for moderate-conservative portfolios."},
    "VOO": {"name": "Vanguard S&P 500 ETF", "price": 498.60, "change_1d": "+0.72%", "pe": 22.8, "forward_pe": 20.5, "market_cap": "485B (AUM)", "52w_high": 512.30, "52w_low": 408.50, "dividend_yield": "1.32%", "analyst_rating": "N/A", "price_target": "N/A", "sector": "Broad Market", "beta": 1.00, "revenue_growth": "N/A", "eps_growth": "N/A", "summary": "S&P 500 index fund. 0.03% expense ratio. Core equity holding. Top-heavy with Magnificent 7 at ~30% weight."}
}

# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_client_portfolio(client_id: str, portfolio_type: str = None):
    """Get client portfolio holdings, allocations, and performance from the database.

    Args:
        client_id: The client ID
        portfolio_type: Optional filter for portfolio type (e.g., 'Growth', 'Conservative Income')

    Returns:
        Portfolio information including holdings, allocations, gains/losses, and performance metrics
    """
    try:
        logger.info(f"🔧 Tool: get_client_portfolio({client_id}, {portfolio_type})")

        # Try DynamoDB first
        client_profile = get_client_profile_from_db(client_id)
        portfolio_data = get_portfolio_from_db(client_id, portfolio_type)

        if not client_profile:
            client_profile = SAMPLE_CLIENT_PROFILES.get(client_id)
        if not portfolio_data:
            portfolio_data = SAMPLE_PORTFOLIOS.get(client_id)

        if not client_profile:
            return f"❌ Client ID '{client_id}' not found. Please verify the client ID."

        if not portfolio_data:
            return f"❌ No portfolio found for client '{client_id}'."

        # Format portfolio as a single dict if it came from sample data
        if isinstance(portfolio_data, dict):
            port = portfolio_data
        elif isinstance(portfolio_data, list) and len(portfolio_data) > 0:
            port = portfolio_data[0]
        else:
            return f"❌ No portfolio data available for client '{client_id}'."

        result = f"""✅ **Client Portfolio Summary**

**Client:** {client_profile.get('name', 'Unknown')}
**Account Type:** {client_profile.get('account_type', 'Standard')}
**Risk Tolerance:** {client_profile.get('risk_tolerance', 'Unknown')}
**Investment Horizon:** {client_profile.get('investment_horizon', 'Unknown')}

**Portfolio:** {port.get('portfolio_type', 'General')}
**Total Value:** ${port.get('total_value', 0):,.2f}
**Cost Basis:** ${port.get('cost_basis', 0):,.2f}
**Unrealized Gain/Loss:** ${port.get('unrealized_gain', 0):,.2f} ({port.get('unrealized_gain_pct', 0):.2f}%)
**Last Rebalance:** {port.get('last_rebalance', 'N/A')}

**Holdings:**
"""
        holdings = port.get('holdings', [])
        for h in holdings:
            gain_str = f"+{h['gain_pct']:.2f}%" if h.get('gain_pct', 0) >= 0 else f"{h['gain_pct']:.2f}%"
            result += f"  {h['ticker']:6s} | {h['name']:30s} | {h['shares']:>6} shares | ${h['current_price']:>9.2f} | ${h['value']:>12,.2f} | {h['weight']:>5.1f}% | {gain_str}\n"

        allocation = port.get('allocation', {})
        if allocation:
            result += "\n**Asset Allocation:**\n"
            for category, pct in allocation.items():
                result += f"  {category}: {pct}%\n"

        goals = client_profile.get('goals', [])
        if goals:
            result += "\n**Investment Goals:**\n"
            for goal in goals:
                result += f"  - {goal}\n"

        return result

    except Exception as e:
        logger.error(f"Error in get_client_portfolio: {e}")
        return f"❌ Error retrieving portfolio: {str(e)}"


@tool
def analyze_market_sector(sector: str, timeframe: str = "1M"):
    """Analyze market sector performance, trends, and outlook.

    Args:
        sector: Sector name (e.g., 'technology', 'healthcare', 'energy', 'financials', 'consumer_discretionary', 'real_estate')
        timeframe: Analysis timeframe - '1D', '1W', '1M', '3M', 'YTD', '1Y' (default: '1M')

    Returns:
        Sector analysis including performance, key drivers, risks, and sentiment
    """
    try:
        logger.info(f"🔧 Tool: analyze_market_sector({sector}, {timeframe})")

        sector_key = sector.lower().replace(" ", "_")
        data = SECTOR_DATA.get(sector_key)

        if not data:
            available = ", ".join(SECTOR_DATA.keys())
            return f"❌ Sector '{sector}' not found. Available sectors: {available}"

        perf = data['performance']

        result = f"""📊 **{data['sector']} Sector Analysis**
**Index:** {data['index']}
**Sentiment:** {data['sentiment']}

**Performance:**
  1-Day: {perf['1D']}  |  1-Week: {perf['1W']}  |  1-Month: {perf['1M']}
  3-Month: {perf['3M']}  |  YTD: {perf['YTD']}  |  1-Year: {perf['1Y']}

**Fundamentals:**
  P/E Ratio: {data['pe_ratio']}
  Dividend Yield: {data['dividend_yield']}%
  Market Cap: ${data['market_cap_T']}T

**Top Holdings:** {', '.join(data['top_holdings'])}

**Key Drivers:**
"""
        for driver in data['key_drivers']:
            result += f"  ✅ {driver}\n"

        result += "\n**Risks:**\n"
        for risk in data['risks']:
            result += f"  ⚠️ {risk}\n"

        return result

    except Exception as e:
        logger.error(f"Error in analyze_market_sector: {e}")
        return f"❌ Error analyzing sector: {str(e)}"


@tool
def get_market_indicators():
    """Get current economic indicators including Fed rates, CPI, GDP, unemployment, and market indices.

    Returns:
        Current economic indicators with values, trends, and market summary
    """
    try:
        logger.info("🔧 Tool: get_market_indicators()")

        data = ECONOMIC_INDICATORS
        result = f"""📈 **Economic Indicators Dashboard**
**Last Updated:** {data['last_updated']}

"""
        for name, info in data['indicators'].items():
            trend_icon = "📈" if info['trend'] == "Increasing" else "📉" if info['trend'] == "Decreasing" else "➡️"
            result += f"  {trend_icon} **{name}:** {info['value']}  (prev: {info['previous']}, trend: {info['trend']})\n"

        result += f"\n**Market Summary:**\n{data['market_summary']}"
        return result

    except Exception as e:
        logger.error(f"Error in get_market_indicators: {e}")
        return f"❌ Error retrieving market indicators: {str(e)}"


@tool
def assess_portfolio_risk(client_id: str):
    """Calculate portfolio risk metrics including beta, Sharpe ratio, volatility, and diversification score.

    Args:
        client_id: The client ID

    Returns:
        Portfolio risk assessment with metrics, risk breakdown, and recommendations
    """
    try:
        logger.info(f"🔧 Tool: assess_portfolio_risk({client_id})")

        portfolio_data = SAMPLE_PORTFOLIOS.get(client_id)
        client_profile = SAMPLE_CLIENT_PROFILES.get(client_id)

        if not portfolio_data or not client_profile:
            return f"❌ Client '{client_id}' not found. Cannot assess risk."

        holdings = portfolio_data.get('holdings', [])
        allocation = portfolio_data.get('allocation', {})

        # Calculate weighted beta
        total_value = portfolio_data.get('total_value', 1)
        weighted_beta = 0
        for h in holdings:
            ticker = h['ticker']
            stock = STOCK_ANALYSIS_DATA.get(ticker, {})
            beta = stock.get('beta', 1.0)
            weight = h.get('value', 0) / total_value
            weighted_beta += beta * weight

        # Determine risk metrics based on portfolio composition
        risk_tolerance = client_profile.get('risk_tolerance', 'Moderate')
        num_holdings = len(holdings)

        if 'Aggressive' in risk_tolerance:
            volatility = 22.5
            sharpe = 1.42
            max_drawdown = -18.5
            var_95 = -3.2
        elif 'Conservative' in risk_tolerance:
            volatility = 9.8
            sharpe = 1.15
            max_drawdown = -8.2
            var_95 = -1.4
        else:
            volatility = 15.2
            sharpe = 1.28
            max_drawdown = -13.8
            var_95 = -2.1

        # Concentration risk
        top_holding_weight = max(h.get('weight', 0) for h in holdings) if holdings else 0
        top_3_weight = sum(sorted([h.get('weight', 0) for h in holdings], reverse=True)[:3])

        concentration_risk = "Low" if top_holding_weight < 10 else "Moderate" if top_holding_weight < 20 else "High"

        # Sector diversification
        num_sectors = len(allocation)
        diversification_score = min(10, num_sectors * 1.2 + (num_holdings * 0.3))

        result = f"""🛡️ **Portfolio Risk Assessment**

**Client:** {client_profile.get('name', 'Unknown')}
**Risk Tolerance:** {risk_tolerance}
**Portfolio Type:** {portfolio_data.get('portfolio_type', 'General')}
**Total Value:** ${total_value:,.2f}

**Risk Metrics:**
  Portfolio Beta: {weighted_beta:.2f}
  Annualized Volatility: {volatility:.1f}%
  Sharpe Ratio: {sharpe:.2f}
  Max Drawdown (12M): {max_drawdown:.1f}%
  Value at Risk (95%, 1-day): {var_95:.1f}%

**Concentration Analysis:**
  Number of Holdings: {num_holdings}
  Top Holding Weight: {top_holding_weight:.1f}%
  Top 3 Holdings Weight: {top_3_weight:.1f}%
  Concentration Risk: {concentration_risk}
  Sector Diversification: {num_sectors} sectors
  Diversification Score: {diversification_score:.1f}/10

**Risk Alignment:**
"""
        # Check if risk profile matches tolerance
        if 'Aggressive' in risk_tolerance and weighted_beta > 1.2:
            result += "  ✅ Portfolio risk level MATCHES aggressive risk tolerance\n"
        elif 'Conservative' in risk_tolerance and weighted_beta < 0.8:
            result += "  ✅ Portfolio risk level MATCHES conservative risk tolerance\n"
        elif 'Moderate' in risk_tolerance and 0.8 <= weighted_beta <= 1.3:
            result += "  ✅ Portfolio risk level MATCHES moderate risk tolerance\n"
        else:
            result += f"  ⚠️ Portfolio beta ({weighted_beta:.2f}) may not fully align with {risk_tolerance} tolerance\n"

        result += "\n**Recommendations:**\n"
        if concentration_risk == "High":
            result += "  ⚠️ Consider reducing concentration in top holdings to manage single-stock risk\n"
        if num_holdings < 8:
            result += "  ⚠️ Consider adding more positions for better diversification\n"
        if weighted_beta > 1.5:
            result += "  ⚠️ High beta exposure — consider hedging with low-beta or bond positions\n"
        if 'Bonds' not in str(allocation) and 'Fixed Income' not in str(allocation):
            result += "  💡 Consider adding fixed income allocation for risk reduction\n"
        if diversification_score >= 7:
            result += "  ✅ Good diversification across sectors and asset classes\n"

        return result

    except Exception as e:
        logger.error(f"Error in assess_portfolio_risk: {e}")
        return f"❌ Error assessing portfolio risk: {str(e)}"


@tool
def get_stock_analysis(ticker: str):
    """Get detailed analysis for a specific stock or ETF including fundamentals, analyst ratings, and outlook.

    Args:
        ticker: Stock or ETF ticker symbol (e.g., 'AAPL', 'MSFT', 'VOO')

    Returns:
        Stock analysis including price, fundamentals, analyst consensus, and summary
    """
    try:
        ticker = ticker.upper().strip()
        logger.info(f"🔧 Tool: get_stock_analysis({ticker})")

        data = STOCK_ANALYSIS_DATA.get(ticker)

        if not data:
            available = ", ".join(sorted(STOCK_ANALYSIS_DATA.keys()))
            return f"❌ No analysis available for ticker '{ticker}'. Available: {available}"

        pt = data.get('price_target')
        upside = ""
        if pt and pt != "N/A":
            upside_pct = ((pt - data['price']) / data['price']) * 100
            upside = f" (upside: {upside_pct:+.1f}%)"

        result = f"""📊 **{data['name']} ({ticker})**
**Sector:** {data['sector']}

**Price & Performance:**
  Current Price: ${data['price']:.2f}  ({data['change_1d']} today)
  52-Week High: ${data['52w_high']:.2f}
  52-Week Low: ${data['52w_low']:.2f}
  Beta: {data['beta']}

**Fundamentals:**
  P/E Ratio: {data['pe']}
  Forward P/E: {data['forward_pe']}
  Market Cap: ${data['market_cap']}
  Dividend Yield: {data['dividend_yield']}
  Revenue Growth: {data['revenue_growth']}
  EPS Growth: {data['eps_growth']}

**Analyst Consensus:**
  Rating: {data['analyst_rating']}
  Price Target: ${pt}{upside}

**Summary:**
{data['summary']}
"""
        return result

    except Exception as e:
        logger.error(f"Error in get_stock_analysis: {e}")
        return f"❌ Error analyzing {ticker}: {str(e)}"


@tool
def get_memory_context(client_id: str, session_id: str = None):
    """Retrieve conversation history and memory context for a client.

    Args:
        client_id: The client ID
        session_id: Optional session ID for specific conversation

    Returns:
        Previous conversation context if available
    """
    try:
        logger.info(f"🔧 Tool: get_memory_context({client_id}, {session_id})")
        context = get_conversation_context(client_id, session_id or "default")
        if context:
            return f"📝 Previous conversation context:\n{context}"
        return "📝 No previous conversation history found for this client."
    except Exception as e:
        logger.error(f"Error retrieving memory context: {e}")
        return "📝 Could not retrieve conversation history."


@tool
def save_conversation_memory(client_id: str, user_message: str, agent_response: str, session_id: str = None):
    """Save a conversation turn to memory for future context.

    Args:
        client_id: The client ID
        user_message: The client's message
        agent_response: Marcus's response
        session_id: Optional session ID

    Returns:
        Confirmation of save
    """
    try:
        logger.info(f"🔧 Tool: save_conversation_memory({client_id})")
        save_conversation_to_memory(client_id, session_id or "default", user_message, agent_response)
        return "✅ Conversation saved to memory."
    except Exception as e:
        logger.error(f"Error saving conversation memory: {e}")
        return "⚠️ Could not save conversation to memory."


# ============================================================================
# AGENT SETUP
# ============================================================================

# Cross-agent orchestration tool
try:
    from cross_agent import invoke_peer_agent, get_available_agents
    CROSS_AGENT_AVAILABLE = True
except ImportError:
    CROSS_AGENT_AVAILABLE = False

@tool
def consult_financial_planner(query: str, client_id: str = ""):
    """Consult Sophia (Financial Planner) for portfolio allocation advice, retirement projections, or rebalancing recommendations.

    Args:
        query: The question to ask Sophia
        client_id: The client ID for context

    Returns:
        Sophia's analysis and recommendations
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('sophia', query, client_id)

@tool
def consult_tax_optimizer(query: str, client_id: str = ""):
    """Consult Olivia (Tax Optimizer) for tax implications of investment decisions.

    Args:
        query: The tax-related question
        client_id: The client ID for context

    Returns:
        Olivia's tax analysis
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('olivia', query, client_id)


# ── Indian Market / Groww Integration Tools ─────────────────────────

try:
    from groww_connector import GrowwConnector, calculate_indian_tax_impact, get_indian_market_hours, NIFTY50_STOCKS, NSE_SECTOR_MAP
    GROWW_AVAILABLE = True
except ImportError:
    GROWW_AVAILABLE = False

@tool
def get_indian_market_status():
    """Get current Indian stock market (NSE/BSE) status, trading hours, and session info.
    Use this when clients ask about Indian market timing or whether markets are open."""
    if not GROWW_AVAILABLE:
        from datetime import timezone
        now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        is_weekday = now_ist.weekday() < 5
        market_open = now_ist.replace(hour=9, minute=15)
        market_close = now_ist.replace(hour=15, minute=30)
        is_open = is_weekday and market_open <= now_ist <= market_close
        return json.dumps({
            'ist_time': now_ist.strftime('%Y-%m-%d %H:%M:%S IST'),
            'market_open': is_open,
            'session': 'trading' if is_open else 'closed',
            'exchange': 'NSE/BSE',
        })
    return json.dumps(get_indian_market_hours())


@tool
def get_nse_stock_quote(ticker: str):
    """Get live quote for an Indian stock on NSE/BSE.
    Use this when clients ask about specific Indian stocks like RELIANCE, TCS, INFY, HDFCBANK etc.

    Args:
        ticker: NSE trading symbol (e.g., RELIANCE, TCS, INFY, HDFCBANK)
    """
    ticker = ticker.upper().replace('.NS', '').replace('.BSE', '').strip()

    sector = NSE_SECTOR_MAP.get(ticker, 'Other') if GROWW_AVAILABLE else 'Unknown'
    is_nifty50 = ticker in (NIFTY50_STOCKS if GROWW_AVAILABLE else [])

    dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
    try:
        response = dynamodb_client.get_item(
            TableName='wealth_mgmt_market_data',
            Key={
                'symbol': {'S': f"{ticker}.NS"},
                'data_type': {'S': 'quote'}
            }
        )
        if 'Item' in response:
            item = response['Item']
            return json.dumps({
                'ticker': ticker,
                'exchange': 'NSE',
                'price': item.get('price', {}).get('N', '0'),
                'change_percent': item.get('change_percent', {}).get('N', '0'),
                'sector': sector,
                'nifty50': is_nifty50,
                'source': 'cached',
            })
    except Exception:
        pass

    return json.dumps({
        'ticker': ticker,
        'exchange': 'NSE',
        'sector': sector,
        'nifty50': is_nifty50,
        'note': 'Live quote requires Groww connection. Use sync_groww_portfolio to connect.',
        'suggestion': f'For {ticker} analysis, I can provide sector outlook and portfolio context from existing data.',
    })


@tool
def calculate_india_tax(client_id: str, sell_tickers: str = ""):
    """Calculate Indian capital gains tax (STCG/LTCG) for selling stocks.
    Applies FY 2024-25 rates: STCG 20%, LTCG 12.5% above 1.25L exemption.

    Args:
        client_id: The client ID to look up holdings for
        sell_tickers: Comma-separated tickers to sell (empty = calculate for all holdings)
    """
    portfolio_data = get_portfolio_from_db(client_id, 'groww_stocks')
    if not portfolio_data:
        portfolio_data = get_portfolio_from_db(client_id)
    if not portfolio_data:
        return json.dumps({'error': 'No portfolio found. Sync Groww data first.'})

    holdings = portfolio_data.get('holdings', [])
    if not holdings:
        return json.dumps({'error': 'No holdings found in portfolio.'})

    holdings_for_calc = []
    sell_list = [t.strip().upper() for t in sell_tickers.split(',') if t.strip()] if sell_tickers else None

    for h in holdings:
        holdings_for_calc.append({
            'ticker': h.get('ticker', h.get('name', '')),
            'quantity': int(h.get('shares', h.get('quantity', 0))),
            'avg_price': float(h.get('avg_cost', h.get('cost_basis', 0))),
            'current_price': float(h.get('current_price', h.get('value', 0)) /
                                   max(int(h.get('shares', 1)), 1)),
            'purchase_date': h.get('purchase_date', ''),
        })

    if GROWW_AVAILABLE:
        result = calculate_indian_tax_impact(holdings_for_calc, sell_list)
    else:
        stcg = sum(
            (h['current_price'] - h['avg_price']) * h['quantity']
            for h in holdings_for_calc
            if (h['current_price'] - h['avg_price']) > 0
        )
        result = {
            'stcg_gains': round(stcg, 2),
            'stcg_tax_20pct': round(stcg * 0.20, 2),
            'ltcg_exemption': 125000,
            'note': 'Approximate calculation. Connect Groww for precise holding period data.',
            'rates': 'STCG: 20%, LTCG: 12.5% (above 1.25L exemption)',
        }

    return json.dumps(result, default=str)


@tool
def sync_groww_portfolio(client_id: str, auth_token: str = ""):
    """Sync portfolio data from Groww brokerage into WealthAI system.
    Pulls stocks, mutual funds, and order history with read-only access.

    Args:
        client_id: WealthAI client ID to sync data for
        auth_token: Groww authentication token (read-only)
    """
    if not GROWW_AVAILABLE:
        return json.dumps({
            'status': 'error',
            'message': 'Groww connector not available. Ensure groww_connector.py is in the shared directory.',
        })

    env_token = os.environ.get('GROWW_AUTH_TOKEN', '')
    token = auth_token or env_token
    if not token:
        return json.dumps({
            'status': 'needs_auth',
            'message': 'Please provide your Groww read-only auth token to sync portfolio data.',
            'how_to_get_token': 'Log into Groww web > Developer Tools > Network tab > Copy Authorization header value',
            'alternative': 'Or set GROWW_AUTH_TOKEN in shared/.env file',
        })

    try:
        connector = GrowwConnector(auth_token=token)
        result = connector.sync_to_dynamodb(client_id)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({'status': 'error', 'message': str(e)})


@tool
def analyze_indian_sector(sector: str):
    """Analyze an Indian market sector with NSE-specific data.
    Sectors: Technology, Banking, FMCG, Pharma, Energy, Auto, Metals, Telecom, Infrastructure, Finance, Power.

    Args:
        sector: Indian market sector name
    """
    sector_stocks = {
        'Technology': ['TCS', 'INFY', 'HCLTECH', 'WIPRO', 'TECHM', 'LTIM'],
        'Banking': ['HDFCBANK', 'ICICIBANK', 'SBIN', 'KOTAKBANK', 'AXISBANK', 'INDUSINDBK'],
        'FMCG': ['ITC', 'HINDUNILVR', 'NESTLEIND', 'BRITANNIA', 'TATACONSUM'],
        'Pharma': ['SUNPHARMA', 'DRREDDY', 'CIPLA', 'DIVISLAB', 'APOLLOHOSP'],
        'Energy': ['RELIANCE', 'ONGC', 'BPCL', 'NTPC', 'POWERGRID'],
        'Auto': ['MARUTI', 'TATAMOTORS', 'M_M', 'BAJAJ_AUTO', 'HEROMOTOCO', 'EICHERMOT'],
        'Metals': ['TATASTEEL', 'JSWSTEEL', 'HINDALCO', 'COALINDIA'],
        'Finance': ['BAJFINANCE', 'BAJAJFINSV', 'SBILIFE', 'HDFCLIFE'],
        'Infrastructure': ['LT', 'ADANIENT', 'ULTRACEMCO', 'GRASIM', 'SHREECEM'],
        'Telecom': ['BHARTIARTL'],
        'Consumer': ['TITAN', 'ASIANPAINT'],
    }

    sector_title = sector.title()
    stocks = sector_stocks.get(sector_title, [])

    if not stocks:
        available = ', '.join(sector_stocks.keys())
        return json.dumps({
            'error': f'Sector "{sector}" not found.',
            'available_sectors': available,
        })

    return json.dumps({
        'sector': sector_title,
        'exchange': 'NSE',
        'market': 'India',
        'key_stocks': stocks,
        'stock_count': len(stocks),
        'nifty50_representation': sum(1 for s in stocks if s in (NIFTY50_STOCKS if GROWW_AVAILABLE else [])),
        'analysis_note': f'Indian {sector_title} sector with {len(stocks)} major constituents on NSE.',
        'index': f'NIFTY{sector_title.upper()}' if sector_title in ['IT', 'Bank', 'Pharma', 'Metal'] else 'NIFTY50',
    })


model = BedrockModel(
    model_id=MODEL_ID,
)

base_tools = [
    get_client_portfolio,
    analyze_market_sector,
    get_market_indicators,
    assess_portfolio_risk,
    get_stock_analysis,
    get_memory_context,
    save_conversation_memory,
    consult_financial_planner,
    consult_tax_optimizer,
    get_indian_market_status,
    get_nse_stock_quote,
    calculate_india_tax,
    sync_groww_portfolio,
    analyze_indian_sector,
]

agent = Agent(
    model=model,
    tools=base_tools,
    system_prompt="""You are Marcus, a senior market analyst at WealthAI Advisors — a wealth management firm specializing in data-driven investment strategies.

CRITICAL: You MUST use your tools to provide accurate information. Never guess or make up market data, portfolio values, or economic indicators.

🔧 **MANDATORY Tool Usage Rules:**
1. When a client provides their ID or asks about their portfolio, ALWAYS use get_client_portfolio tool FIRST
2. When asked about market sectors, ALWAYS use analyze_market_sector tool
3. When asked about economic conditions or indicators, ALWAYS use get_market_indicators tool
4. When asked to evaluate risk, ALWAYS use assess_portfolio_risk tool
5. When asked about specific stocks or ETFs, ALWAYS use get_stock_analysis tool
6. NEVER provide financial data without using the tools first

📊 **Your Available Tools:**
- get_client_portfolio(client_id, portfolio_type=None): Look up client holdings, allocations, and performance
- analyze_market_sector(sector, timeframe="1M"): Get sector performance, drivers, and outlook
- get_market_indicators(): Get current economic indicators (Fed rates, CPI, GDP, etc.)
- assess_portfolio_risk(client_id): Calculate risk metrics (beta, Sharpe, volatility, diversification)
- get_stock_analysis(ticker): Get detailed analysis for a stock or ETF
- get_memory_context(client_id, session_id=None): Retrieve conversation history
- save_conversation_memory(client_id, user_message, agent_response, session_id=None): Save conversation context
- consult_financial_planner(query, client_id): Ask Sophia (Financial Planner) for portfolio allocation, retirement projections, or rebalancing advice
- consult_tax_optimizer(query, client_id): Ask Olivia (Tax Optimizer) for tax-loss harvesting, capital gains, or tax bracket strategies
- get_indian_market_status(): Check if NSE/BSE is open, current IST time, trading session
- get_nse_stock_quote(ticker): Get quote for Indian stocks (RELIANCE, TCS, INFY, HDFCBANK, etc.)
- calculate_india_tax(client_id, sell_tickers=""): Calculate STCG/LTCG tax under Indian rules (FY 2024-25)
- sync_groww_portfolio(client_id, auth_token=""): Sync holdings from Groww brokerage (read-only)
- analyze_indian_sector(sector): Analyze Indian market sectors (Technology, Banking, FMCG, Pharma, etc.)

🎯 **Critical Response Patterns:**
1. Client asks about their portfolio → IMMEDIATELY use get_client_portfolio
2. Client asks about sectors/markets → IMMEDIATELY use analyze_market_sector
3. Client asks about economy/rates/inflation → IMMEDIATELY use get_market_indicators
4. Client asks about risk → IMMEDIATELY use assess_portfolio_risk
5. Client asks about a specific stock → IMMEDIATELY use get_stock_analysis
6. Client asks for a comprehensive review → Use MULTIPLE tools (portfolio + risk + indicators)
7. Client asks about retirement planning, allocation changes, or rebalancing → Use consult_financial_planner to get Sophia's input
8. Client asks about tax implications of trades or tax-efficient strategies → Use consult_tax_optimizer to get Olivia's input
9. Client asks about Indian stocks (RELIANCE, TCS, etc.) → Use get_nse_stock_quote
10. Client asks about NSE/BSE market timing → Use get_indian_market_status
11. Client asks about Indian tax on selling stocks → Use calculate_india_tax (STCG 20%, LTCG 12.5%)
12. Client asks to connect Groww portfolio → Use sync_groww_portfolio
13. Client asks about Indian sectors (Banking, IT, Pharma) → Use analyze_indian_sector

💼 **Professional Standards:**
- Always provide data-backed analysis, never speculation
- Include both opportunities and risks in every recommendation
- Reference specific numbers and metrics from tool results
- When making recommendations, explain the reasoning clearly
- Acknowledge uncertainty and limitations
- Remind clients that past performance does not guarantee future results
- Note that this is informational analysis, not personalized financial advice

🚨 **IMPORTANT DISCLAIMERS:**
- Always remind clients that analysis is for informational purposes
- Recommend consulting with their financial advisor for major decisions
- Never guarantee returns or predict exact market movements
- Be transparent about data limitations and assumptions

Be professional, approachable, and thorough. Use clear language that clients can understand, avoiding unnecessary jargon. When presenting data, organize it clearly with headers and bullet points."""
)

# ============================================================================
# AGENTCORE ENTRYPOINT
# ============================================================================

@app.entrypoint
def marcus_market_analyst_agent(payload, context):
    """
    Marcus Market Analyst Agent with complete memory, session, and DynamoDB integration
    """
    request_start = time.time()
    try:
        user_input = payload.get("prompt", "Hello! How can I help you with your investments today?")
        client_id = payload.get("customer_id", "")
        session_id = context.session_id or ""

        logger.info(f"📈 Marcus Agent - Processing request for client: {client_id}")
        logger.info(f"🔗 Session ID: {session_id}")

        current_agent = agent

        if client_id or session_id:
            mem_start = time.time()
            initialize_memory(client_id, session_id)
            logger.info(f"🧠 Using unified memory with actor_id={client_id}, session_id={session_id}")

            if MEMORY_TOOLS_AVAILABLE and client_id:
                memory_provider = initialize_memory_tools(client_id, session_id)
                if memory_provider and hasattr(memory_provider, 'tools'):
                    try:
                        enhanced_tools = base_tools + memory_provider.tools
                        current_agent = Agent(model=model, tools=enhanced_tools)
                        logger.info(f"✅ Enhanced agent with {len(memory_provider.tools)} memory tools")
                    except Exception as e:
                        logger.warning(f"Could not enhance agent with memory tools: {e}")

        conv_context = ""
        if client_id:
            try:
                ctx_start = time.time()
                conv_context = get_conversation_context(client_id, session_id)
                ctx_ms = (time.time() - ctx_start) * 1000
                if conv_context:
                    logger.info(f"🧠 Retrieved conversation context: {len(conv_context)} characters")
                    if metrics:
                        metrics.track_memory(hit=True, retrieval_ms=ctx_ms)
                elif metrics:
                    metrics.track_memory(hit=False, retrieval_ms=ctx_ms)
            except Exception as e:
                logger.warning(f"Could not retrieve context: {e}")
                if metrics:
                    metrics.track_memory(hit=False)

        enhanced_input = user_input
        if client_id:
            enhanced_input = f"Client ID: {client_id}\n\n{user_input}"
        if conv_context:
            enhanced_input = f"Previous conversation context:\n{conv_context}\n\nCurrent request: {enhanced_input}"

        response = current_agent(enhanced_input)

        # Handle different response structures safely
        try:
            if hasattr(response, 'message') and response.message:
                if isinstance(response.message, dict) and 'content' in response.message:
                    content = response.message['content']
                    if isinstance(content, list) and len(content) > 0:
                        first_content = content[0]
                        if isinstance(first_content, dict) and 'text' in first_content:
                            result = first_content['text']
                        else:
                            result = str(first_content)
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
            logger.error(f"❌ Error parsing response structure: {e}")
            result = "I apologize, but I encountered a response processing error. Please try again."

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
        logger.error(f"❌ Error in Marcus agent: {e}")
        if metrics:
            request_latency = (time.time() - request_start) * 1000
            metrics.emit_agent_response(latency_ms=request_latency, input_tokens=0, output_tokens=0)
        return f"I apologize, but I encountered an error processing your request: {str(e)}. Please try again or contact support."

if __name__ == "__main__":
    app.run()
