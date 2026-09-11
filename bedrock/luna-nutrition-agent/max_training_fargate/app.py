#!/usr/bin/env python3
"""
Max Training Agent - LangGraph with Flask HTTP Server
Simple HTTP wrapper for Fargate deployment with ADOT observability
"""
import os
import json
import logging
import boto3
import uuid
from typing import Annotated
from typing_extensions import TypedDict
from decimal import Decimal
from datetime import datetime

# Flask for HTTP server
from flask import Flask, request, jsonify
from flask_cors import CORS

# OpenTelemetry for session ID propagation
try:
    from opentelemetry import baggage
    from opentelemetry.context import attach
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    print("⚠️  OpenTelemetry baggage not available - session propagation limited")

# LangGraph imports
from langchain.chat_models import init_chat_model

# Configuration reader
from config_reader import get_config
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool

print("=" * 60, flush=True)
print("🚀 Max Training Agent - Flask HTTP Server", flush=True)
print("=" * 60, flush=True)

# Configure logging with DEBUG level for detailed observability
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Load configuration
logger.info("📋 Loading configuration from config.conf...")
config = get_config()
AWS_REGION = config.get_aws_region()
MODEL_ID = config.get_max_agent_config()['model_id']
TABLES = config.get_dynamodb_tables()
SERVICE_NAME = config.get_max_agent_config()['service_name_full']

logger.info(f"✅ AWS Region: {AWS_REGION}")
logger.info(f"✅ Model ID: {MODEL_ID}")
logger.info(f"✅ Service Name: {SERVICE_NAME}")
logger.debug(f"🔍 Logging level: DEBUG (detailed observability enabled)")
logger.debug(f"🔍 OTEL Available: {OTEL_AVAILABLE}")

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
logger.info("✅ DynamoDB client initialized")
logger.debug(f"🔍 Tables: {TABLES}")

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

# ============================================================================
# LANGCHAIN TOOLS
# ============================================================================

@tool
def get_customer_info(customer_id: str) -> str:
    """Get customer and pet information from database.
    
    Args:
        customer_id: The customer ID (e.g., 'cust_john_doe')
    
    Returns:
        Customer information including name, pets, and appointment history
    """
    try:
        logger.info(f"🔧 Tool: get_customer_info({customer_id})")
        logger.debug(f"🔍 Extracting username from customer_id: {customer_id}")
        
        # Extract username from customer_id
        username = customer_id.replace('cust_', '') if customer_id.startswith('cust_') else customer_id
        logger.debug(f"🔍 Username: {username}")
        
        # Query user_auth table
        table = dynamodb.Table(TABLES['user_auth'])
        logger.debug(f"🔍 Querying DynamoDB table: {TABLES['user_auth']}")
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(username)
        )
        
        items = response.get('Items', [])
        logger.debug(f"🔍 DynamoDB returned {len(items)} items")
        if not items:
            logger.debug(f"🔍 Customer not found: {customer_id}")
            return f"❌ Customer '{customer_id}' not found."
        
        user = decimal_to_native(items[0])
        
        result = f"""✅ Customer: {user.get('name', 'Unknown')}
Email: {user.get('email', 'N/A')}
Phone: {user.get('phone', 'N/A')}
Membership: {user.get('membership_level', 'Basic')}

🐾 Pets:"""
        
        pets = user.get('pets', [])
        if pets:
            for i, pet in enumerate(pets, 1):
                result += f"\n{i}. {pet.get('name')} - {pet.get('breed')} ({pet.get('species')}, {pet.get('age')} years)"
                if pet.get('allergies'):
                    result += f"\n   ⚠️  Allergies: {pet.get('allergies')}"
        else:
            result += "\nNo pets registered."
        
        return result
        
    except Exception as e:
        logger.error(f"Error in get_customer_info: {e}")
        return f"❌ Error retrieving customer info: {str(e)}"

@tool
def get_training_services() -> str:
    """Get list of available training services with pricing.
    
    Returns:
        Formatted list of training services, descriptions, and prices
    """
    services = {
        "Basic Obedience": {"price": 75, "duration": "1 hour", "description": "Sit, stay, come, heel"},
        "Advanced Obedience": {"price": 100, "duration": "1 hour", "description": "Off-leash control, distance commands"},
        "Puppy Training": {"price": 60, "duration": "45 minutes", "description": "Socialization, basic commands"},
        "Behavioral Modification": {"price": 125, "duration": "1.5 hours", "description": "Aggression, anxiety, fear"},
        "Agility Training": {"price": 90, "duration": "1 hour", "description": "Obstacle course, coordination"},
        "Private Session": {"price": 150, "duration": "1 hour", "description": "One-on-one customized training"}
    }
    
    result = "🎓 Available Training Services:\n\n"
    for i, (name, details) in enumerate(services.items(), 1):
        result += f"{i}. {name} - ${details['price']}\n"
        result += f"   Duration: {details['duration']}\n"
        result += f"   Focus: {details['description']}\n\n"
    
    return result

@tool
def book_training_appointment(
    customer_id: str,
    pet_name: str,
    service_type: str,
    date: str,
    time: str,
    notes: str = ""
) -> str:
    """Book a training appointment for a customer's pet.
    
    Args:
        customer_id: Customer ID (e.g., 'cust_john_doe')
        pet_name: Name of the pet
        service_type: Type of training service
        date: Appointment date (YYYY-MM-DD)
        time: Appointment time (HH:MM AM/PM)
        notes: Optional notes about the appointment
    
    Returns:
        Confirmation message with appointment details
    """
    try:
        logger.info(f"🔧 Tool: book_training_appointment({customer_id}, {pet_name}, {service_type})")
        
        # Service pricing
        service_prices = {
            "basic obedience": 75,
            "advanced obedience": 100,
            "puppy training": 60,
            "behavioral modification": 125,
            "agility training": 90,
            "private session": 150
        }
        
        service_durations = {
            "basic obedience": "1 hour",
            "advanced obedience": "1 hour",
            "puppy training": "45 minutes",
            "behavioral modification": "1.5 hours",
            "agility training": "1 hour",
            "private session": "1 hour"
        }
        
        service_key = service_type.lower()
        price = service_prices.get(service_key, 100)
        duration = service_durations.get(service_key, "1 hour")
        
        # Create appointment
        appointment_id = str(uuid.uuid4())
        appointment = {
            'appointment_id': appointment_id,
            'customer_id': customer_id,
            'pet_name': pet_name,
            'service_type': service_type,
            'service_category': 'training',
            'date': date,
            'time': time,
            'duration': duration,
            'price': Decimal(str(price)),
            'status': 'scheduled',
            'notes': notes,
            'created_at': datetime.now().isoformat()
        }
        
        # Save to DynamoDB
        table = dynamodb.Table(TABLES['appointments'])
        table.put_item(Item=appointment)
        
        result = f"""✅ Training Appointment Booked!

📋 Appointment ID: {appointment_id}
👤 Customer: {customer_id}
🐾 Pet: {pet_name}
🎓 Service: {service_type}
📅 Date: {date}
🕐 Time: {time}
⏱️  Duration: {duration}
💰 Price: ${price}
📝 Notes: {notes if notes else 'None'}

Your training session has been confirmed. We'll send a reminder 24 hours before the appointment."""
        
        return result
        
    except Exception as e:
        logger.error(f"Error in book_training_appointment: {e}")
        return f"❌ Error booking appointment: {str(e)}"

# ============================================================================
# LANGGRAPH SETUP
# ============================================================================

# Initialize LLM
llm = init_chat_model(
    model=MODEL_ID,
    model_provider="bedrock_converse",
    temperature=0.7,
    region_name=AWS_REGION
)
logger.info("✅ LLM initialized")

# Define tools
tools = [get_customer_info, get_training_services, book_training_appointment]
llm_with_tools = llm.bind_tools(tools)
logger.info(f"✅ {len(tools)} tools configured")

# Define state
class State(TypedDict):
    messages: Annotated[list, add_messages]
    customer_id: str
    session_id: str

# Define chatbot node
def chatbot(state: State):
    """Process messages and generate responses"""
    logger.info("🤖 Chatbot node invoked")
    logger.debug(f"🔍 State keys: {list(state.keys())}")
    logger.debug(f"🔍 Message count: {len(state.get('messages', []))}")
    
    # Build system message
    system_content = """You are Max, an expert dog training assistant for a pet store.

Your expertise:
- Dog training programs (obedience, behavioral, agility)
- Training techniques and methods
- Behavioral problem solving
- Puppy socialization

Your personality:
- Professional and knowledgeable
- Patient and encouraging
- Enthusiastic about dog training
- Clear and practical advice

Available tools:
- get_customer_info(customer_id): Look up customer and pet details
- get_training_services(): Show available training programs
- book_training_appointment(customer_id, pet_name, service_type, date, time, notes): Schedule training

When customers ask about their pets or want to book training, use the appropriate tools."""
    
    # Add customer context if available
    customer_id = state.get('customer_id', '')
    logger.debug(f"🔍 Customer ID from state: {customer_id}")
    if customer_id and customer_id != 'anonymous':
        logger.debug(f"🔍 Adding customer context to system message")
        system_content += f"""

- The customer you're talking to has ID: {customer_id}
- When they ask about "my pets", use get_customer_info({customer_id})
- DO NOT ask for their customer ID - you already have it!"""
    
    # Prepare messages
    messages = [{"role": "system", "content": system_content}] + state["messages"]
    
    # Invoke LLM
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

# Build graph
graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)

# Add tool node
tool_node = ToolNode(tools=tools)
graph_builder.add_node("tools", tool_node)

# Add edges
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

# Compile graph
graph = graph_builder.compile()
logger.info("✅ LangGraph compiled")

# ============================================================================
# FLASK HTTP SERVER
# ============================================================================

flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "agent": SERVICE_NAME,
        "framework": "langgraph",
        "tools": len(tools),
        "model": MODEL_ID
    }), 200

@flask_app.route('/', methods=['GET'])
def root():
    """Root endpoint with agent info"""
    return jsonify({
        "agent": "Max Training Agent",
        "description": "Expert dog training assistant",
        "framework": "LangGraph",
        "tools": [tool.name for tool in tools],
        "endpoints": {
            "health": "/health",
            "invoke": "/invoke (POST)"
        }
    }), 200

@flask_app.route('/invoke', methods=['POST'])
def invoke_agent():
    """Agent invocation endpoint with comprehensive observability support"""
    try:
        payload = request.get_json()
        
        # Extract parameters
        prompt = payload.get('prompt', '')
        customer_id = payload.get('customer_id', payload.get('customerId', 'anonymous'))
        trace_id = payload.get('trace_id', payload.get('traceId', ''))
        
        # ============================================================================
        # Generate session ID: {customer_id}_{agent_name}_{unique_id}
        # Format: cust_sarah_wilson_max_abc123xyz
        # ============================================================================
        agent_name = "max"
        
        # Check if session ID provided in header (takes precedence)
        header_session_id = request.headers.get('X-Amzn-Bedrock-AgentCore-Runtime-Session-Id', '')
        
        if header_session_id:
            # Use provided session ID from header
            bedrock_session_id = header_session_id
            logger.debug(f"🔍 Using session ID from header: {bedrock_session_id}")
        else:
            # Generate session ID: customer_id + agent_name + unique_suffix
            # Extract clean customer identifier
            if customer_id and customer_id != 'anonymous':
                # Remove 'cust_' prefix if present for cleaner format
                clean_customer = customer_id.replace('cust_', '') if customer_id.startswith('cust_') else customer_id
                # Generate unique suffix (8 characters)
                unique_suffix = str(uuid.uuid4()).replace('-', '')[:8]
                # Format: customername_agentname_uniqueid
                bedrock_session_id = f"{clean_customer}_{agent_name}_{unique_suffix}"
                logger.debug(f"🔍 Generated session ID: {bedrock_session_id}")
            else:
                # Anonymous user - use standard UUID format
                bedrock_session_id = f"anonymous_{agent_name}_{str(uuid.uuid4())}"
                logger.debug(f"🔍 Generated anonymous session ID: {bedrock_session_id}")
        
        # ============================================================================
        # Extract ALL observability headers for comprehensive tracing
        # ============================================================================
        
        # X-Ray trace ID (AWS format)
        # Format: Root=1-5759e988-bd862e3fe1be46a994272793;Parent=53995c3f42cd8ad8;Sampled=1
        xray_trace_id = request.headers.get('X-Amzn-Trace-Id', '')
        
        # W3C traceparent (standard format)
        # Format: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
        traceparent = request.headers.get('traceparent', '')
        
        # W3C tracestate (vendor-specific tracing info)
        # Format: congo=t61rcWkgMzE,rojo=00f067aa0ba902b7
        tracestate = request.headers.get('tracestate', '')
        
        # MCP session ID
        mcp_session_id = request.headers.get('mcp-session-id', '')
        
        # W3C baggage (context propagation)
        # Format: userId=alice,serverRegion=us-east-1
        baggage_header = request.headers.get('baggage', '')
        
        if not prompt:
            return jsonify({"error": "Missing 'prompt' in request"}), 400
        
        # Log all observability context
        logger.info(f"📥 Invoke: customer={customer_id}, session={bedrock_session_id}")
        
        if xray_trace_id:
            logger.info(f"🔍 X-Ray Trace ID: {xray_trace_id}")
        if traceparent:
            logger.info(f"🔍 W3C traceparent: {traceparent}")
        if tracestate:
            logger.info(f"🔍 W3C tracestate: {tracestate}")
        if mcp_session_id:
            logger.info(f"🔍 MCP Session ID: {mcp_session_id}")
        if baggage_header:
            logger.info(f"🔍 W3C baggage: {baggage_header}")
        if trace_id:
            logger.info(f"🔍 Payload trace_id: {trace_id}")
        
        logger.info(f"💬 Prompt: {prompt[:100]}...")
        
        # ============================================================================
        # Set session ID and baggage in OpenTelemetry for proper propagation
        # ============================================================================
        token = None
        if OTEL_AVAILABLE and bedrock_session_id:
            try:
                # Start with session ID
                ctx = baggage.set_baggage("session.id", bedrock_session_id)
                
                # Add MCP session ID if present
                if mcp_session_id:
                    ctx = baggage.set_baggage("mcp.session.id", mcp_session_id, context=ctx)
                
                # Add customer ID for user tracking
                if customer_id and customer_id != 'anonymous':
                    ctx = baggage.set_baggage("user.id", customer_id, context=ctx)
                
                # Parse and add W3C baggage items if present
                if baggage_header:
                    for item in baggage_header.split(','):
                        if '=' in item:
                            key, value = item.strip().split('=', 1)
                            ctx = baggage.set_baggage(key, value, context=ctx)
                
                token = attach(ctx)
                logger.info(f"🔗 OTEL baggage configured with session and context")
                logger.info(f"   - session.id: {bedrock_session_id}")
                if mcp_session_id:
                    logger.info(f"   - mcp.session.id: {mcp_session_id}")
                if customer_id != 'anonymous':
                    logger.info(f"   - user.id: {customer_id}")
            except Exception as e:
                logger.warning(f"⚠️  Could not set OTEL baggage: {e}")
        
        # Prepare state with comprehensive observability context
        state = {
            "messages": [{"role": "user", "content": prompt}],
            "customer_id": customer_id,
            "session_id": bedrock_session_id,
            "trace_id": trace_id or xray_trace_id or traceparent,
            "observability": {
                "xray_trace_id": xray_trace_id,
                "traceparent": traceparent,
                "tracestate": tracestate,
                "mcp_session_id": mcp_session_id,
                "baggage": baggage_header
            }
        }
        
        # Log comprehensive trace context
        logger.info(f"🔗 Comprehensive observability context prepared:")
        logger.info(f"   - Primary trace: {trace_id or xray_trace_id or traceparent or 'auto-generated'}")
        logger.info(f"   - Session: {bedrock_session_id}")
        if mcp_session_id:
            logger.info(f"   - MCP Session: {mcp_session_id}")
        
        logger.debug(f"🔍 Full state object:")
        logger.debug(f"   - messages: {len(state['messages'])} message(s)")
        logger.debug(f"   - customer_id: {state['customer_id']}")
        logger.debug(f"   - session_id: {state['session_id']}")
        logger.debug(f"   - trace_id: {state['trace_id']}")
        logger.debug(f"   - observability keys: {list(state['observability'].keys())}")
        
        # Invoke graph
        result = graph.invoke(state)
        
        # Extract response
        response_message = result["messages"][-1]
        response_content = response_message.content if hasattr(response_message, 'content') else str(response_message)
        
        logger.info(f"✅ Response generated ({len(response_content)} chars)")
        
        # Build response with comprehensive observability metadata
        response_data = {
            "response": response_content,
            "session_id": bedrock_session_id,
            "customer_id": customer_id,
            "model": MODEL_ID,
            "observability": {
                "trace_id": trace_id or xray_trace_id or traceparent,
                "session_id": bedrock_session_id
            }
        }
        
        # Include additional observability IDs if provided
        if mcp_session_id:
            response_data["observability"]["mcp_session_id"] = mcp_session_id
        if xray_trace_id:
            response_data["observability"]["xray_trace_id"] = xray_trace_id
        if traceparent:
            response_data["observability"]["traceparent"] = traceparent
        
        # Detach OTEL context if it was attached
        if token is not None:
            try:
                from opentelemetry.context import detach
                detach(token)
            except Exception as e:
                logger.debug(f"🔍 OTEL context cleanup: {e}")
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"❌ Error in invoke: {e}")
        # Detach OTEL context on error if it was attached
        if 'token' in locals() and token is not None:
            try:
                from opentelemetry.context import detach
                detach(token)
            except:
                pass
        return jsonify({"error": str(e)}), 500

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    logger.info("🚀 Starting Flask HTTP server on 0.0.0.0:8080")
    flask_app.run(host='0.0.0.0', port=8080, debug=False)
