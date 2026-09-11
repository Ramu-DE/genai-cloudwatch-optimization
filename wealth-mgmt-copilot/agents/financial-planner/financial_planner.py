#!/usr/bin/env python3
"""
Financial Planner Agent - Complete Implementation with Memory & Session Management
Integrates all DynamoDB, memory, and session logic as Strands tools
"""
import os
import sys
import logging
import boto3
import json
import time
import uuid
import calendar
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

# Configure logging
log_file = os.path.join(os.path.expanduser('~'), 'sophia_agent.log')
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

logger.info("📊 SOPHIA FINANCIAL PLANNER AGENT STARTING UP - FULL IMPLEMENTATION")
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
metrics = MetricsEmitter(agent_name='sophia', model_id=MODEL_ID) if METRICS_AVAILABLE else None

# DynamoDB setup
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)

# DynamoDB table names
TABLES = {
    'clients': 'wealth_mgmt_client_profiles',
    'portfolios': 'wealth_mgmt_portfolios',
    'consultations': 'wealth_mgmt_consultations',
    'advisor_schedule': 'wealth_mgmt_advisor_schedule',
    'user_auth': 'wealth_mgmt_user_auth'
}

# Global memory client and memory ID
memory_client = None
memory_id = None
memory_tool_provider = None

# ============================================================================
# FALLBACK DATA (empty — client data loaded from DynamoDB / trading platform)
# ============================================================================

MOCK_CLIENT_PROFILES = {}

MOCK_PORTFOLIOS = {}

MOCK_CONSULTATIONS = {}

ALLOCATION_TEMPLATES = {
    "conservative": {
        "us_equities": 25, "international_equities": 10,
        "fixed_income": 45, "alternatives": 10, "cash": 10
    },
    "moderate": {
        "us_equities": 40, "international_equities": 20,
        "fixed_income": 30, "alternatives": 5, "cash": 5
    },
    "aggressive": {
        "us_equities": 50, "international_equities": 20,
        "fixed_income": 10, "alternatives": 15, "cash": 5
    },
    "retirement_income": {
        "us_equities": 20, "international_equities": 5,
        "fixed_income": 50, "alternatives": 10, "cash": 15
    },
    "education_fund": {
        "us_equities": 35, "international_equities": 15,
        "fixed_income": 35, "alternatives": 5, "cash": 10
    },
    "growth": {
        "us_equities": 55, "international_equities": 25,
        "fixed_income": 5, "alternatives": 10, "cash": 5
    }
}

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
        target_memory_id = os.getenv('BEDROCK_AGENTCORE_MEMORY_ID', 'wealth_mgmt_sophia_planner_agent_memory')
    except Exception as e:
        logger.error(f"Error reading env var: {e}")
        target_memory_id = 'wealth_mgmt_sophia_planner_agent_memory'

    if memory_id:
        logger.info(f"📊 Using cached unified memory ID: {memory_id}")
        return memory_id

    try:
        logger.info("📊 Initializing unified AgentCore Memory with long-term strategies...")
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
                description="Unified persistent memory for financial planner agent - stores all client interactions",
                strategies=[
                    {
                        "summaryMemoryStrategy": {
                            "name": "PlanningSessionSummarizer",
                            "description": "Summarizes financial planning consultations across all clients",
                            "namespaces": ["/summaries/sophia/{actorId}/{sessionId}"]
                        }
                    },
                    {
                        "semanticMemoryStrategy": {
                            "name": "FinancialPlanningKnowledge",
                            "description": "Stores financial planning facts, strategies, and recommendations",
                            "namespaces": ["/knowledge/sophia/{actorId}/planning"]
                        }
                    },
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": "ClientPlanningPreferences",
                            "description": "Learns client financial planning preferences and investment patterns",
                            "namespaces": ["/preferences/sophia/{actorId}"]
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
                    logger.error(f"Could not find existing unified memory with name: {target_memory_id}")
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
        namespace = f"/preferences/sophia/{client_id}"
        memory_tool_provider = AgentCoreMemoryToolProvider(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id or "default",
            namespace=namespace,
            region=AWS_REGION
        )
        logger.info(f"✅ Memory tool provider initialized with unified memory")
        logger.info(f"🗂️ Actor (client_id): {client_id}, Session: {session_id or 'default'}")
        logger.info(f"🗂️ Namespace: {namespace}")
        return memory_tool_provider

    except Exception as e:
        logger.error(f"⚠️ Could not initialize memory tool provider: {e}")
        return None

def save_conversation_to_memory(client_id, session_id, user_message, sophia_response):
    """Save conversation turn to unified AgentCore Memory with length management"""
    global memory_client, memory_id

    if not memory_id or not memory_client:
        logger.debug("💾 Memory not available - skipping save")
        return

    try:
        logger.info(f"💾 Saving to unified memory: Client={client_id}, Session={session_id}")
        logger.info(f"💾 User='{user_message[:30]}...', Planner='{sophia_response[:30]}...'")

        max_length = 8500

        truncated_user_message = user_message
        if len(user_message) > max_length:
            truncated_user_message = user_message[:max_length] + "... [truncated]"
            logger.warning(f"⚠️ User message truncated from {len(user_message)} to {len(truncated_user_message)} chars")

        truncated_sophia_response = sophia_response
        if len(sophia_response) > max_length:
            half_length = max_length // 2
            truncated_sophia_response = (
                sophia_response[:half_length] +
                "... [middle truncated] ..." +
                sophia_response[-half_length:]
            )
            logger.warning(f"⚠️ Planner response truncated from {len(sophia_response)} to {len(truncated_sophia_response)} chars")

        memory_client.create_event(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
            messages=[
                (truncated_user_message, "user"),
                (truncated_sophia_response, "assistant")
            ]
        )
        logger.info("✅ Successfully saved to unified memory")

    except Exception as e:
        logger.error(f"⚠️ Could not save to memory: {e}")

def get_conversation_context(client_id, session_id):
    """Get recent conversation context from unified AgentCore Memory"""
    global memory_client, memory_id

    if not memory_id or not memory_client:
        logger.debug("📊 Memory not initialized, attempting to initialize...")
        initialize_memory(client_id, session_id)

    if not memory_id or not memory_client:
        logger.debug("📊 Memory not available - no context")
        return ""

    try:
        logger.info(f"📊 Checking if session {session_id} exists for client {client_id}...")
        session_exists = False
        try:
            events = memory_client.list_events(
                memory_id=memory_id,
                actor_id=client_id,
                session_id=session_id
            )
            session_exists = len(events) > 0
            logger.info(f"✅ Session exists: {session_exists} (found {len(events)} events)")
        except Exception as e:
            logger.warning(f"⚠️ Error checking session existence: {e}")
            session_exists = False

        if not session_exists:
            logger.info(f"📝 No existing conversation found for session {session_id}")
            return ""

        logger.info(f"📚 Loading conversation history for existing session {session_id}")
        recent_turns = memory_client.get_last_k_turns(
            memory_id=memory_id,
            actor_id=client_id,
            session_id=session_id,
            k=5
        )

        if recent_turns:
            context = "Recent conversation history:\n"
            for turn in recent_turns:
                role = turn.get('role', 'unknown')
                content = turn.get('content', '')
                if content:
                    context += f"- {role}: {content[:200]}...\n" if len(content) > 200 else f"- {role}: {content}\n"
            logger.info(f"✅ Retrieved {len(recent_turns)} conversation turns")
            return context

        return ""

    except Exception as e:
        logger.error(f"⚠️ Could not retrieve conversation context: {e}")
        return ""

def validate_consultation_availability(preferred_date, preferred_time):
    """Validate consultation date and time against business rules"""
    try:
        parsed_date = None
        date_formats = ['%B %d, %Y', '%B %dth, %Y', '%B %dst, %Y', '%B %dnd, %Y', '%B %drd, %Y',
                       '%d %B %Y', '%d %B', '%B %d', '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']

        for fmt in date_formats:
            try:
                if 'Y' not in fmt:
                    test_date = f"{preferred_date}, 2026"
                    parsed_date = datetime.strptime(test_date, f"{fmt}, %Y")
                else:
                    parsed_date = datetime.strptime(preferred_date, fmt)
                break
            except ValueError:
                continue

        if not parsed_date:
            return {
                'available': False,
                'message': f"I couldn't understand the date format '{preferred_date}'. Please use formats like 'September 20, 2026' or '09/20/2026'."
            }

        if parsed_date.year < 2026:
            parsed_date = parsed_date.replace(year=2026)

        current_date = datetime.now()
        if parsed_date.date() < current_date.date():
            return {
                'available': False,
                'message': f"Cannot schedule consultations in the past. Please choose a date from {current_date.strftime('%B %d, %Y')} onwards."
            }

        if parsed_date.weekday() >= 5:
            day_name = calendar.day_name[parsed_date.weekday()]
            next_monday = parsed_date + timedelta(days=(7 - parsed_date.weekday()))
            return {
                'available': False,
                'message': f"{preferred_date} falls on a {day_name}. We are closed on weekends. The next available weekday is {next_monday.strftime('%B %d, %Y')} (Monday)."
            }

        time_formats = ['%I:%M %p', '%I:%M%p', '%I %p', '%I%p', '%H:%M']
        parsed_time = None
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(preferred_time.strip(), fmt).time()
                break
            except ValueError:
                continue

        if not parsed_time:
            return {
                'available': False,
                'message': f"I couldn't understand the time format '{preferred_time}'. Please use formats like '10:00 AM' or '14:00'."
            }

        business_start = datetime.strptime("09:00", "%H:%M").time()
        business_end = datetime.strptime("17:00", "%H:%M").time()

        if parsed_time < business_start or parsed_time > business_end:
            return {
                'available': False,
                'message': f"Our business hours are 9:00 AM to 5:00 PM, Monday through Friday. The requested time {preferred_time} is outside our operating hours."
            }

        return {
            'available': True,
            'validated_date': parsed_date.strftime('%Y-%m-%d'),
            'validated_time': parsed_time.strftime('%H:%M'),
            'message': 'Available'
        }

    except Exception as e:
        logger.error(f"Error validating consultation availability: {e}")
        return {
            'available': False,
            'message': "Error validating consultation time. Please try again with a clear date and time format."
        }

def extract_conversation_context(user_input):
    """Extract key context from user input to improve agent understanding"""
    context = {}

    if any(word in user_input.lower() for word in ["retire", "retirement", "pension", "401k", "ira"]):
        context['topic'] = 'retirement'
    elif any(word in user_input.lower() for word in ["college", "education", "529", "tuition"]):
        context['topic'] = 'education'
    elif any(word in user_input.lower() for word in ["house", "home", "mortgage", "down payment"]):
        context['topic'] = 'home_purchase'
    elif any(word in user_input.lower() for word in ["rebalance", "allocation", "diversif"]):
        context['topic'] = 'rebalancing'
    elif any(word in user_input.lower() for word in ["risk", "volatility", "conservative", "aggressive"]):
        context['topic'] = 'risk_assessment'

    if any(word in user_input.lower() for word in ["schedule", "book", "meeting", "consultation", "appointment"]):
        context['action'] = 'schedule'
    elif any(word in user_input.lower() for word in ["change", "modify", "update", "reschedule"]):
        context['action'] = 'modify'
    elif any(word in user_input.lower() for word in ["cancel", "remove"]):
        context['action'] = 'cancel'
    elif any(word in user_input.lower() for word in ["recommend", "suggest", "advise"]):
        context['action'] = 'recommend'

    return context

# ============================================================================
# DynamoDB HELPER FUNCTIONS
# ============================================================================

def get_client_profile_from_db(client_id: str):
    """Get client profile from DynamoDB, falling back to mock data"""
    try:
        log_dynamodb_request("GetItem", TABLES['clients'], key={"client_id": client_id})
        start_time = time.time()

        table = dynamodb_resource.Table(TABLES['clients'])
        response = table.get_item(Key={'client_id': client_id})
        duration = time.time() - start_time
        log_dynamodb_response("GetItem", response, duration)

        if 'Item' in response:
            return decimal_to_native(response['Item'])
    except Exception as e:
        logger.warning(f"DynamoDB lookup failed for {client_id}: {e}")

    if client_id in MOCK_CLIENT_PROFILES:
        logger.info(f"📊 Using mock data for client: {client_id}")
        return MOCK_CLIENT_PROFILES[client_id]

    return None

def get_portfolio_from_db(client_id: str):
    """Get portfolio data from DynamoDB, falling back to mock data"""
    try:
        log_dynamodb_request("GetItem", TABLES['portfolios'], key={"client_id": client_id})
        start_time = time.time()

        table = dynamodb_resource.Table(TABLES['portfolios'])
        response = table.get_item(Key={'client_id': client_id})
        duration = time.time() - start_time
        log_dynamodb_response("GetItem", response, duration)

        if 'Item' in response:
            return decimal_to_native(response['Item'])
    except Exception as e:
        logger.warning(f"DynamoDB portfolio lookup failed for {client_id}: {e}")

    if client_id in MOCK_PORTFOLIOS:
        logger.info(f"📊 Using mock portfolio data for client: {client_id}")
        return MOCK_PORTFOLIOS[client_id]

    return None

def get_consultations_from_db(client_id: str):
    """Get consultations from DynamoDB, falling back to mock data"""
    try:
        log_dynamodb_request("Scan", TABLES['consultations'])
        start_time = time.time()

        table = dynamodb_resource.Table(TABLES['consultations'])
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('client_id').eq(client_id)
        )
        duration = time.time() - start_time
        log_dynamodb_response("Scan", response, duration)

        if response.get('Items'):
            return decimal_to_native(response['Items'])
    except Exception as e:
        logger.warning(f"DynamoDB consultation lookup failed for {client_id}: {e}")

    if client_id in MOCK_CONSULTATIONS:
        logger.info(f"📊 Using mock consultation data for client: {client_id}")
        return MOCK_CONSULTATIONS[client_id]

    return []

def save_consultation_to_db(consultation_data):
    """Save consultation to DynamoDB"""
    try:
        log_dynamodb_request("PutItem", TABLES['consultations'], item=consultation_data)
        start_time = time.time()

        table = dynamodb_resource.Table(TABLES['consultations'])
        response = table.put_item(Item=consultation_data)
        duration = time.time() - start_time
        log_dynamodb_response("PutItem", response, duration)

        return True
    except Exception as e:
        logger.error(f"Failed to save consultation: {e}")
        return False

# ============================================================================
# STRANDS TOOLS
# ============================================================================

@tool
def get_client_profile(client_id: str):
    """Get full client profile including risk assessment, financial goals, and net worth.

    Args:
        client_id: The client ID

    Returns:
        Complete client profile with financial details and goals
    """
    try:
        logger.info(f"📊 Tool: get_client_profile({client_id})")
        profile = get_client_profile_from_db(client_id)

        if not profile:
            return json.dumps({
                "error": f"Client profile not found for ID: {client_id}",
                "suggestion": "Please verify the client ID. Register via the login page to create your account."
            })

        portfolio = get_portfolio_from_db(client_id)

        result = {
            "client_id": profile.get("client_id"),
            "name": profile.get("name"),
            "age": profile.get("age"),
            "email": profile.get("email"),
            "annual_income": profile.get("annual_income"),
            "net_worth": profile.get("net_worth"),
            "risk_tolerance": profile.get("risk_tolerance"),
            "investment_horizon": profile.get("investment_horizon"),
            "goals": profile.get("goals", []),
            "tax_filing_status": profile.get("tax_filing_status"),
            "state": profile.get("state"),
            "assigned_advisor": profile.get("advisor"),
        }

        if portfolio:
            result["portfolio_summary"] = {
                "total_value": portfolio.get("total_value"),
                "ytd_return": portfolio.get("ytd_return"),
                "one_year_return": portfolio.get("one_year_return"),
                "three_year_annualized": portfolio.get("three_year_annualized"),
                "last_updated": portfolio.get("last_updated")
            }

        logger.info(f"✅ Client profile retrieved: {profile.get('name')}")
        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error getting client profile: {e}")
        return json.dumps({"error": f"Error retrieving client profile: {str(e)}"})


@tool
def recommend_allocation(client_id: str, risk_level: str = None, goal: str = None):
    """Generate asset allocation recommendation based on client risk profile and goals.

    Args:
        client_id: The client ID
        risk_level: Override risk level ('conservative', 'moderate', 'aggressive'). If None, uses client profile.
        goal: Specific goal to optimize for ('retirement', 'education', 'home_purchase', 'growth')

    Returns:
        Recommended allocation with rationale
    """
    try:
        logger.info(f"📊 Tool: recommend_allocation({client_id}, risk={risk_level}, goal={goal})")

        profile = get_client_profile_from_db(client_id)
        portfolio = get_portfolio_from_db(client_id)

        if not profile:
            return json.dumps({"error": f"Client not found: {client_id}"})

        effective_risk = risk_level or profile.get("risk_tolerance", "moderate")

        if goal and goal in ALLOCATION_TEMPLATES:
            template_key = goal
        elif effective_risk in ALLOCATION_TEMPLATES:
            template_key = effective_risk
        else:
            template_key = "moderate"

        recommended = ALLOCATION_TEMPLATES[template_key]

        age = profile.get("age", 40)
        if age >= 55:
            recommended = {k: v for k, v in recommended.items()}
            shift = min(5, recommended.get("us_equities", 0))
            recommended["us_equities"] = recommended.get("us_equities", 40) - shift
            recommended["fixed_income"] = recommended.get("fixed_income", 30) + shift

        result = {
            "client_name": profile.get("name"),
            "risk_tolerance": effective_risk,
            "optimization_goal": goal or "general",
            "recommended_allocation": recommended,
            "rationale": []
        }

        result["rationale"].append(f"Based on {effective_risk} risk tolerance for a {age}-year-old investor")
        if goal:
            result["rationale"].append(f"Optimized for {goal.replace('_', ' ')} goal")
        if age >= 55:
            result["rationale"].append("Age-adjusted: shifted 5% from equities to fixed income for capital preservation")

        if portfolio:
            current = portfolio.get("current_allocation", {})
            deviations = {}
            for asset_class, target_pct in recommended.items():
                current_data = current.get(asset_class, {})
                current_pct = current_data.get("pct", 0) if isinstance(current_data, dict) else 0
                diff = target_pct - current_pct
                if abs(diff) >= 2:
                    deviations[asset_class] = {
                        "current": current_pct,
                        "recommended": target_pct,
                        "action": "increase" if diff > 0 else "decrease",
                        "change": abs(diff)
                    }

            result["rebalancing_needed"] = deviations
            result["current_portfolio_value"] = portfolio.get("total_value")

        logger.info(f"✅ Allocation recommendation generated for {profile.get('name')}")
        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error generating allocation: {e}")
        return json.dumps({"error": f"Error generating recommendation: {str(e)}"})


@tool
def calculate_retirement_projection(client_id: str, retirement_age: int = 65, monthly_contribution: float = None):
    """Calculate retirement projections based on current portfolio and contributions.

    Args:
        client_id: The client ID
        retirement_age: Target retirement age (default 65)
        monthly_contribution: Monthly investment amount. If None, estimated from income.

    Returns:
        Retirement projection with savings trajectory and probability of meeting goal
    """
    try:
        logger.info(f"📊 Tool: calculate_retirement_projection({client_id}, age={retirement_age}, contrib={monthly_contribution})")

        profile = get_client_profile_from_db(client_id)
        portfolio = get_portfolio_from_db(client_id)

        if not profile:
            return json.dumps({"error": f"Client not found: {client_id}"})

        current_age = profile.get("age", 40)
        years_to_retirement = max(1, retirement_age - current_age)
        current_savings = portfolio.get("total_value", 0) if portfolio else 0
        annual_income = profile.get("annual_income", 100000)

        if monthly_contribution is None:
            monthly_contribution = annual_income * 0.15 / 12

        retirement_goals = [g for g in profile.get("goals", []) if g.get("type") == "retirement"]
        target_amount = retirement_goals[0].get("target_amount", 2000000) if retirement_goals else 2000000

        risk = profile.get("risk_tolerance", "moderate")
        return_assumptions = {
            "conservative": {"expected": 0.055, "low": 0.03, "high": 0.07},
            "moderate": {"expected": 0.07, "low": 0.04, "high": 0.10},
            "aggressive": {"expected": 0.09, "low": 0.05, "high": 0.13}
        }
        returns = return_assumptions.get(risk, return_assumptions["moderate"])

        projections = {}
        for scenario, annual_return in returns.items():
            monthly_return = annual_return / 12
            n_months = years_to_retirement * 12

            if monthly_return > 0:
                future_value = (
                    current_savings * (1 + monthly_return) ** n_months +
                    monthly_contribution * (((1 + monthly_return) ** n_months - 1) / monthly_return)
                )
            else:
                future_value = current_savings + monthly_contribution * n_months

            projections[scenario] = round(future_value, 2)

        expected_fv = projections["expected"]
        gap = target_amount - expected_fv
        on_track = expected_fv >= target_amount

        if not on_track and years_to_retirement > 0:
            monthly_return = returns["expected"] / 12
            n_months = years_to_retirement * 12
            fv_current = current_savings * (1 + monthly_return) ** n_months
            remaining = target_amount - fv_current
            if monthly_return > 0:
                required_monthly = remaining / (((1 + monthly_return) ** n_months - 1) / monthly_return)
            else:
                required_monthly = remaining / n_months
        else:
            required_monthly = monthly_contribution

        result = {
            "client_name": profile.get("name"),
            "current_age": current_age,
            "retirement_age": retirement_age,
            "years_to_retirement": years_to_retirement,
            "current_portfolio_value": current_savings,
            "monthly_contribution": round(monthly_contribution, 2),
            "annual_contribution": round(monthly_contribution * 12, 2),
            "target_amount": target_amount,
            "projections": {
                "expected_scenario": {"annual_return": f"{returns['expected']*100:.1f}%", "projected_value": projections["expected"]},
                "low_scenario": {"annual_return": f"{returns['low']*100:.1f}%", "projected_value": projections["low"]},
                "high_scenario": {"annual_return": f"{returns['high']*100:.1f}%", "projected_value": projections["high"]}
            },
            "on_track": on_track,
            "gap_or_surplus": round(abs(gap), 2),
            "gap_type": "surplus" if on_track else "shortfall",
            "required_monthly_contribution": round(required_monthly, 2) if not on_track else None,
            "assumptions": {
                "risk_profile": risk,
                "inflation_adjusted": False,
                "includes_social_security": False
            }
        }

        logger.info(f"✅ Retirement projection complete for {profile.get('name')}: {'On track' if on_track else 'Shortfall'}")
        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error calculating retirement projection: {e}")
        return json.dumps({"error": f"Error calculating projection: {str(e)}"})


@tool
def schedule_consultation(client_id: str, advisor_name: str, preferred_date: str, preferred_time: str, consultation_type: str):
    """Schedule a financial planning consultation with an advisor.

    Args:
        client_id: The client ID
        advisor_name: Name of the financial advisor
        preferred_date: Desired date (e.g., 'September 25, 2026' or '2026-09-25')
        preferred_time: Desired time (e.g., '10:00 AM' or '14:00')
        consultation_type: Type of consultation ('annual_review', 'retirement_planning', 'estate_planning', 'tax_planning', 'portfolio_review', 'initial_consultation')

    Returns:
        Confirmation of scheduled consultation
    """
    try:
        logger.info(f"📊 Tool: schedule_consultation({client_id}, {advisor_name}, {preferred_date}, {preferred_time}, {consultation_type})")

        profile = get_client_profile_from_db(client_id)
        if not profile:
            return json.dumps({"error": f"Client not found: {client_id}"})

        validation = validate_consultation_availability(preferred_date, preferred_time)
        if not validation['available']:
            return json.dumps({
                "scheduled": False,
                "message": validation['message']
            })

        consultation_id = f"cons_{uuid.uuid4().hex[:8]}"
        consultation_data = {
            "consultation_id": consultation_id,
            "client_id": client_id,
            "client_name": profile.get("name"),
            "advisor": advisor_name,
            "date": validation['validated_date'],
            "time": validation['validated_time'],
            "type": consultation_type,
            "status": "scheduled",
            "created_at": datetime.now().isoformat(),
            "notes": f"{consultation_type.replace('_', ' ').title()} consultation for {profile.get('name')}"
        }

        saved = save_consultation_to_db(consultation_data)

        result = {
            "scheduled": True,
            "consultation_id": consultation_id,
            "client_name": profile.get("name"),
            "advisor": advisor_name,
            "date": validation['validated_date'],
            "time": validation['validated_time'],
            "type": consultation_type,
            "saved_to_database": saved,
            "message": f"Consultation scheduled with {advisor_name} on {validation['validated_date']} at {validation['validated_time']} for {consultation_type.replace('_', ' ')}."
        }

        logger.info(f"✅ Consultation scheduled: {consultation_id}")
        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error scheduling consultation: {e}")
        return json.dumps({"error": f"Error scheduling consultation: {str(e)}"})


@tool
def list_client_consultations(client_id: str):
    """Get all upcoming consultations for a client.

    Args:
        client_id: The client ID

    Returns:
        List of scheduled consultations with details
    """
    try:
        logger.info(f"📊 Tool: list_client_consultations({client_id})")

        consultations = get_consultations_from_db(client_id)

        if not consultations:
            return json.dumps({
                "client_id": client_id,
                "consultations": [],
                "message": "No consultations found for this client."
            })

        today = datetime.now().strftime('%Y-%m-%d')
        upcoming = [c for c in consultations if c.get('date', '') >= today]
        past = [c for c in consultations if c.get('date', '') < today]

        result = {
            "client_id": client_id,
            "upcoming_consultations": sorted(upcoming, key=lambda x: x.get('date', '')),
            "past_consultations_count": len(past),
            "total_consultations": len(consultations)
        }

        logger.info(f"✅ Found {len(upcoming)} upcoming consultations")
        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error listing consultations: {e}")
        return json.dumps({"error": f"Error listing consultations: {str(e)}"})


@tool
def rebalance_portfolio(client_id: str):
    """Analyze current portfolio against target allocation and suggest rebalancing trades.

    Args:
        client_id: The client ID

    Returns:
        Rebalancing analysis with specific trade suggestions
    """
    try:
        logger.info(f"📊 Tool: rebalance_portfolio({client_id})")

        profile = get_client_profile_from_db(client_id)
        portfolio = get_portfolio_from_db(client_id)

        if not profile:
            return json.dumps({"error": f"Client not found: {client_id}"})

        if not portfolio:
            return json.dumps({"error": f"No portfolio data found for: {client_id}"})

        total_value = portfolio.get("total_value", 0)
        current_alloc = portfolio.get("current_allocation", {})
        target_alloc = portfolio.get("target_allocation", {})

        trades = []
        total_drift = 0

        for asset_class, target_pct in target_alloc.items():
            current_data = current_alloc.get(asset_class, {})
            current_pct = current_data.get("pct", 0) if isinstance(current_data, dict) else 0
            drift = target_pct - current_pct
            total_drift += abs(drift)

            if abs(drift) >= 2:
                target_value = total_value * target_pct / 100
                current_value = current_data.get("value", 0) if isinstance(current_data, dict) else 0
                trade_amount = target_value - current_value

                trades.append({
                    "asset_class": asset_class.replace("_", " ").title(),
                    "current_pct": current_pct,
                    "target_pct": target_pct,
                    "drift": round(drift, 1),
                    "action": "BUY" if trade_amount > 0 else "SELL",
                    "amount": round(abs(trade_amount), 2),
                    "holdings": [h.get("ticker") for h in (current_data.get("holdings", []) if isinstance(current_data, dict) else [])]
                })

        needs_rebalancing = total_drift >= 10

        result = {
            "client_name": profile.get("name"),
            "portfolio_value": total_value,
            "total_drift_pct": round(total_drift, 1),
            "needs_rebalancing": needs_rebalancing,
            "urgency": "high" if total_drift >= 20 else "medium" if total_drift >= 10 else "low",
            "suggested_trades": sorted(trades, key=lambda x: abs(x['drift']), reverse=True),
            "ytd_return": portfolio.get("ytd_return"),
            "last_rebalanced": portfolio.get("last_updated"),
            "tax_note": "Consider tax implications before executing trades. Prefer tax-advantaged accounts for rebalancing when possible."
        }

        logger.info(f"✅ Rebalancing analysis complete: drift={total_drift:.1f}%, trades={len(trades)}")
        return json.dumps(result, default=str)

    except Exception as e:
        logger.error(f"Error analyzing rebalancing: {e}")
        return json.dumps({"error": f"Error analyzing portfolio: {str(e)}"})


@tool
def get_memory_context(client_id: str, session_id: str = None):
    """Retrieve conversation history and memory context for a client.

    Args:
        client_id: The client ID
        session_id: Optional session ID

    Returns:
        Recent conversation context and client preferences from memory
    """
    try:
        logger.info(f"📊 Tool: get_memory_context({client_id}, {session_id})")
        context = get_conversation_context(client_id, session_id or "default")
        if context:
            return context
        return "No previous conversation context found for this client."
    except Exception as e:
        logger.error(f"Error retrieving memory context: {e}")
        return "Could not retrieve memory context."


@tool
def save_conversation_memory(client_id: str, user_message: str, agent_response: str, session_id: str = None):
    """Save conversation context to memory for future reference.

    Args:
        client_id: The client ID
        user_message: The user's message
        agent_response: The agent's response
        session_id: Optional session ID

    Returns:
        Confirmation of saved memory
    """
    try:
        logger.info(f"📊 Tool: save_conversation_memory({client_id})")
        save_conversation_to_memory(
            client_id,
            session_id or "default",
            user_message,
            agent_response
        )
        return "Conversation context saved to memory."
    except Exception as e:
        logger.error(f"Error saving conversation memory: {e}")
        return "Could not save conversation to memory."


# ============================================================================
# CROSS-AGENT ORCHESTRATION
# ============================================================================

try:
    from cross_agent import invoke_peer_agent, get_available_agents
    CROSS_AGENT_AVAILABLE = True
except ImportError:
    CROSS_AGENT_AVAILABLE = False

@tool
def consult_market_analyst(query: str, client_id: str = ""):
    """Consult the Market Analyst for stock analysis, market trends, sector performance, or risk assessment.

    Args:
        query: The market-related question to ask the Market Analyst
        client_id: The client ID for context

    Returns:
        Market Analyst's analysis and insights
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('marcus', query, client_id)

@tool
def consult_tax_optimizer(query: str, client_id: str = ""):
    """Consult the Tax Optimizer for tax implications of financial decisions, harvesting opportunities, or tax strategy.

    Args:
        query: The tax-related question to ask the Tax Optimizer
        client_id: The client ID for context

    Returns:
        Tax Optimizer's analysis and recommendations
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('olivia', query, client_id)

@tool
def consult_compliance_checker(query: str, client_id: str = ""):
    """Consult the Compliance Checker for regulatory compliance, KYC status, or trade limit verification.

    Args:
        query: The compliance question to ask the Compliance Checker
        client_id: The client ID for context

    Returns:
        Compliance Checker's assessment
    """
    if not CROSS_AGENT_AVAILABLE:
        return "Cross-agent consultation is not available in this environment."
    return invoke_peer_agent('victor', query, client_id)


# ============================================================================
# AGENT CREATION
# ============================================================================

# Create Bedrock model
model = BedrockModel(
    model_id=MODEL_ID,
)

# Create base tools list
base_tools = [
    get_client_profile,
    recommend_allocation,
    calculate_retirement_projection,
    schedule_consultation,
    list_client_consultations,
    rebalance_portfolio,
    get_memory_context,
    save_conversation_memory,
    consult_market_analyst,
    consult_tax_optimizer,
    consult_compliance_checker,
]

# Create Strands agent with all tools
agent = Agent(
    model=model,
    tools=base_tools,
    system_prompt="""You are the Financial Planner at WealthAI Advisors.

CRITICAL: You MUST use your tools to provide accurate information. Never guess or make up financial data.

🔧 **MANDATORY Tool Usage Rules:**
1. When a client provides a client ID or asks about their profile/portfolio, ALWAYS use get_client_profile tool FIRST
2. When asked about allocation or investment strategy, ALWAYS use recommend_allocation tool
3. When asked about retirement planning or projections, ALWAYS use calculate_retirement_projection tool
4. When asked to schedule meetings, ALWAYS use schedule_consultation tool
5. When asked about rebalancing, ALWAYS use rebalance_portfolio tool
6. NEVER provide client financial information without using the tools first

📊 **Your Available Tools:**
- get_client_profile(client_id): Look up complete client profile, goals, risk tolerance, and portfolio summary
- recommend_allocation(client_id, risk_level=None, goal=None): Generate asset allocation recommendations
- calculate_retirement_projection(client_id, retirement_age=65, monthly_contribution=None): Run retirement projections
- schedule_consultation(client_id, advisor_name, preferred_date, preferred_time, consultation_type): Book advisor meetings
- list_client_consultations(client_id): Get upcoming scheduled consultations
- rebalance_portfolio(client_id): Analyze portfolio drift and suggest rebalancing trades
- get_memory_context(client_id, session_id=None): Retrieve conversation history
- save_conversation_memory(client_id, user_message, agent_response, session_id=None): Save conversation context
- consult_market_analyst(query, client_id): Ask the Market Analyst for market data, stock analysis, sector trends
- consult_tax_optimizer(query, client_id): Ask the Tax Optimizer for tax implications of financial decisions
- consult_compliance_checker(query, client_id): Ask the Compliance Checker for regulatory compliance and trade limit checks

🤝 **Cross-Agent Collaboration:**
- When allocation decisions need market context → consult_market_analyst
- When rebalancing may have tax consequences → consult_tax_optimizer
- When large trades need compliance clearance → consult_compliance_checker

🎯 **Critical Response Patterns:**
1. Client asks about profile/goals → IMMEDIATELY use get_client_profile tool
2. Client asks about allocation/strategy → use recommend_allocation tool
3. Client mentions retirement → use calculate_retirement_projection tool
4. Client wants to book/schedule → use schedule_consultation tool
5. Client asks about rebalancing → use rebalance_portfolio tool

📋 **FINANCIAL PLANNING FOCUS AREAS:**
- Retirement planning and projections (401k, IRA, pension optimization)
- Goal-based investing (education, home purchase, legacy planning)
- Asset allocation and diversification strategies
- Portfolio rebalancing recommendations
- Risk assessment and management
- Consultation scheduling and follow-ups

🚨 **IMPORTANT GUIDELINES:**
- NEVER provide specific stock picks or buy/sell recommendations for individual securities
- Focus on allocation strategies, diversification, and planning
- Always reference actual client data from the database
- When discussing projections, clearly state assumptions and limitations
- For tax-related matters, recommend consulting with the Tax Optimizer agent
- After scheduling consultations, confirm the details saved to the database
- Be empathetic and thorough — financial decisions are personal

🕒 **BUSINESS HOURS & AVAILABILITY:**
- Business Hours: 9:00 AM to 5:00 PM, Monday through Friday ONLY
- CLOSED: Saturdays, Sundays, and US federal holidays
- If client requests weekend/holiday/outside hours: Politely decline and suggest alternative times
- When client doesn't specify time, suggest: "What time would you prefer? Our hours are 9:00 AM to 5:00 PM, Monday-Friday."

Be warm, professional, and data-driven. Always use the appropriate tools and provide personalized financial planning guidance based on each client's unique situation."""
)


@app.entrypoint
def sophia_financial_planner_agent(payload, context):
    """
    Financial Planner Agent with complete memory, session, and DynamoDB integration
    """
    request_start = time.time()
    try:
        user_input = payload.get("prompt", "Hello! How can I help you with your financial planning today?")
        client_id = payload.get("customer_id", "") or payload.get("client_id", "")
        session_id = context.session_id or ""

        logger.info(f"📊 Financial Planner - Processing request for client: {client_id}")
        logger.info(f"🔗 Session ID: {session_id}")

        # Extract context from user input
        conversation_context = extract_conversation_context(user_input)
        if conversation_context:
            logger.info(f"🧠 Extracted context: {conversation_context}")

        # Initialize memory for this client/session
        current_agent = agent

        if client_id or session_id:
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

        # Get conversation context if available
        ctx = ""
        if client_id:
            try:
                ctx_start = time.time()
                ctx = get_conversation_context(client_id, session_id)
                ctx_ms = (time.time() - ctx_start) * 1000
                if ctx:
                    logger.info(f"🧠 Retrieved conversation context: {len(ctx)} characters")
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

        if ctx:
            enhanced_input = f"Previous conversation context:\n{ctx}\n\nCurrent request: {enhanced_input}"

        # Let Strands agent decide which tools to use
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
            logger.error(f"🔍 Response type: {type(response)}")
            logger.error(f"🔍 Response content: {str(response)[:200]}...")
            result = "I apologize, but I encountered a response processing error. Please try again."

        # Save conversation to memory
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
        logger.error(f"❌ Error in Financial Planner agent: {e}")
        if metrics:
            request_latency = (time.time() - request_start) * 1000
            metrics.emit_agent_response(latency_ms=request_latency, input_tokens=0, output_tokens=0)
        return f"I apologize, but I encountered an error: {str(e)}. Please try again or contact support."

if __name__ == "__main__":
    app.run()
