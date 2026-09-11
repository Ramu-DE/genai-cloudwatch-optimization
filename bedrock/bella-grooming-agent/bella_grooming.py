#!/usr/bin/env python3
"""
Bella Grooming Agent - Complete Implementation with Memory & Session Management
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

# Configure logging (reduced verbosity for production)
log_file = os.path.join(os.path.expanduser('~'), 'bella_agent.log')
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

logger.info("🐾 BELLA AGENT STARTING UP - FULL IMPLEMENTATION - FIXED VERSION")
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

# DynamoDB setup
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
dynamodb = boto3.client('dynamodb', region_name=AWS_REGION)

# DynamoDB table names
TABLES = {
    'customers': 'genai_petstore_customer_profiles',
    'appointments': 'genai_petstore_appointments',
    'agencies': 'genai_petstore_staff_schedule',
    'staff_schedule': 'genai_petstore_staff_schedule',
    'user_auth': 'genai_petstore_user_auth'
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

def initialize_memory(customer_id=None, session_id=None):
    """Initialize AgentCore Memory with a single unified memory object"""
    global memory_client, memory_id
    
    if not MEMORY_AVAILABLE:
        logger.warning("⚠️ AgentCore Memory not available - using basic conversation tracking")
        return None
    
    try:
        # Create a single unified memory ID for Bella Grooming
        # This memory will store all customer interactions in one place
        target_memory_id = os.getenv('BEDROCK_AGENTCORE_MEMORY_ID', 'genai_petstore_bella_grooming_agent_memory')
    except Exception as e:
        print(f"An error occurred while retrieving environment variable '{var_name}': {e}")
        target_memory_id = 'genai_petstore_bella_grooming_agent_memory'
    # Check if we already have a memory_id initialized
    if memory_id:
        logger.info(f"🧠 Using cached unified memory ID: {memory_id}")
        return memory_id
    
    try:
        logger.info("🧠 Initializing unified AgentCore Memory with long-term strategies...")
        memory_client = MemoryClient(region_name=AWS_REGION)
        
        # FIRST: List all existing memories and try to find the unified memory
        try:
            memories = memory_client.list_memories()
            
            # Look for the unified memory object
            existing_memory = None
            for m in memories:
                memory_id_field = m.get('id')  # This is the actual memory ID
                
                # Check if our unified memory name is part of the memory ID
                if memory_id_field and target_memory_id in memory_id_field:
                    existing_memory = m
                    break
            
            if existing_memory:
                # Get the memory ID from the found memory (use 'id' field as per documentation)
                memory_id = existing_memory.get('id')
                logger.info(f"✅ Found existing unified memory: {memory_id}")
                return memory_id
                
        except Exception as e:
            logger.warning(f"Error listing memories: {e}")
        
        # SECOND: Try to create new unified memory only if none exists
        try:
            # Note: {actorId} and {sessionId} are template variables that AgentCore replaces
            # with the actual customer_id and session_id when storing/retrieving data
            memory = memory_client.create_memory_and_wait(
                name=target_memory_id,
                description="Unified persistent memory for Bella grooming agent - stores all customer interactions",
                strategies=[
                    {
                        "summaryMemoryStrategy": {
                            "name": "GroomingSessionSummarizer",
                            "description": "Summarizes grooming consultations and appointments across all customers",
                            "namespaces": ["/summaries/bella/{actorId}/{sessionId}"]  # actorId = customer_id
                        }
                    },
                    {
                        "semanticMemoryStrategy": {
                            "name": "GroomingKnowledgeBase",
                            "description": "Stores grooming facts, pet care knowledge, and service information",
                            "namespaces": ["/knowledge/bella/{actorId}/grooming"]  # actorId = customer_id
                        }
                    },
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": "GroomingPreferences",
                            "description": "Learns customer grooming preferences and pet care patterns",
                            "namespaces": ["/preferences/bella/{actorId}"]  # actorId = customer_id
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
            
            # THIRD: If creation failed because it exists, try to find it again
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

def initialize_memory_tools(customer_id, session_id=None):
    """Initialize AgentCore Memory Tool Provider with unified memory object"""
    global memory_tool_provider, memory_id
    
    if not MEMORY_TOOLS_AVAILABLE or not memory_id:
        logger.info("⚠️ Memory tools not available or memory not initialized")
        return None
    
    try:
        # Use unified namespace structure - customer_id is used as actor_id
        # This ensures {actorId} in namespace templates resolves to customer_id
        namespace = f"/preferences/bella/{customer_id}"
        
        memory_tool_provider = AgentCoreMemoryToolProvider(
            memory_id=memory_id,  # Single unified memory object
            actor_id=customer_id,  # Customer ID - maps to {actorId} in namespace templates
            session_id=session_id or "default",  # Session ID - maps to {sessionId} in namespace templates
            namespace=namespace,
            region=AWS_REGION
        )
        
        logger.info(f"✅ Memory tool provider initialized with unified memory")
        logger.info(f"🗂️ Actor (customer_id): {customer_id}, Session: {session_id or 'default'}")
        logger.info(f"🗂️ Namespace: {namespace}")
        return memory_tool_provider
        
    except Exception as e:
        logger.error(f"⚠️ Could not initialize memory tool provider: {e}")
        return None

def save_conversation_to_memory(customer_id, session_id, user_message, bella_response):
    """Save conversation turn to unified AgentCore Memory with length management"""
    global memory_client, memory_id
    
    if not memory_id or not memory_client:
        logger.debug("💾 Memory not available - skipping save")
        return
    
    try:
        logger.info(f"💾 Saving to unified memory: Customer={customer_id}, Session={session_id}")
        logger.info(f"💾 User='{user_message[:30]}...', Bella='{bella_response[:30]}...'")
        
        # Truncate messages if they exceed AgentCore's 9000 character limit
        max_length = 8500  # Leave buffer for metadata
        
        truncated_user_message = user_message
        if len(user_message) > max_length:
            truncated_user_message = user_message[:max_length] + "... [truncated]"
            logger.warning(f"⚠️ User message truncated from {len(user_message)} to {len(truncated_user_message)} chars")
        
        truncated_bella_response = bella_response
        if len(bella_response) > max_length:
            # Intelligent truncation - keep beginning and end
            half_length = max_length // 2
            truncated_bella_response = (
                bella_response[:half_length] + 
                "... [middle truncated] ..." + 
                bella_response[-half_length:]
            )
            logger.warning(f"⚠️ Bella response truncated from {len(bella_response)} to {len(truncated_bella_response)} chars")
        
        # Save to unified memory using customer_id as actor and session_id for conversation tracking
        # The actor_id (customer_id) will be used to populate {actorId} in namespace templates
        memory_client.create_event(
            memory_id=memory_id,  # Single unified memory object
            actor_id=customer_id,  # Customer ID - maps to {actorId} in namespace templates
            session_id=session_id,  # Session ID - maps to {sessionId} in namespace templates
            messages=[
                (truncated_user_message, "user"),
                (truncated_bella_response, "assistant")
            ]
        )
        logger.info("✅ Successfully saved to unified memory")
        logger.debug("🧠 Long-term memory extraction will process this conversation in 2-3 minutes")
        
    except Exception as e:
        logger.error(f"⚠️ Could not save to memory: {e}")

def validate_appointment_availability(preferred_date, preferred_time):
    """Validate appointment date and time against business rules"""
    try:
        from datetime import datetime as dt, timedelta
        import calendar
        
        # Parse and validate date
        parsed_date = None
        date_formats = ['%B %d, %Y', '%B %dth, %Y', '%B %dst, %Y', '%B %dnd, %Y', '%B %drd, %Y', 
                       '%d %B %Y', '%d %B', '%B %d', '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y']
        
        for fmt in date_formats:
            try:
                if 'Y' not in fmt:  # No year specified, use 2025
                    test_date = f"{preferred_date}, 2025"
                    parsed_date = dt.strptime(test_date, f"{fmt}, %Y")
                else:
                    parsed_date = dt.strptime(preferred_date, fmt)
                break
            except ValueError:
                continue
        
        if not parsed_date:
            return {
                'available': False,
                'message': f"❌ I couldn't understand the date format '{preferred_date}'. Please use formats like 'November 15, 2025' or '11/15/2025'."
            }
        
        # Ensure date is not in the past and not before 2025
        if parsed_date.year < 2025:
            parsed_date = parsed_date.replace(year=2025)
        
        current_date = dt.now()
        if parsed_date.date() < current_date.date():
            return {
                'available': False,
                'message': f"❌ Cannot schedule appointments in the past. Please choose a date from {current_date.strftime('%B %d, %Y')} onwards."
            }
        
        # Check if it's a weekend (Saturday = 5, Sunday = 6)
        weekday = parsed_date.weekday()
        if weekday >= 5:  # Saturday or Sunday
            day_name = calendar.day_name[weekday]
            return {
                'available': False,
                'message': f"❌ Sorry, we're closed on {day_name}s. Please choose a weekday (Monday-Friday) for your appointment."
            }
        
        # Check US federal holidays (basic list)
        us_holidays_2025 = [
            dt(2025, 1, 1),   # New Year's Day
            dt(2025, 1, 20),  # Martin Luther King Jr. Day
            dt(2025, 2, 17),  # Presidents' Day
            dt(2025, 5, 26),  # Memorial Day
            dt(2025, 7, 4),   # Independence Day
            dt(2025, 9, 1),   # Labor Day
            dt(2025, 10, 13), # Columbus Day
            dt(2025, 11, 11), # Veterans Day
            dt(2025, 11, 27), # Thanksgiving
            dt(2025, 12, 25), # Christmas Day
        ]
        
        if parsed_date.date() in [h.date() for h in us_holidays_2025]:
            holiday_name = "a US federal holiday"
            return {
                'available': False,
                'message': f"❌ Sorry, we're closed on {parsed_date.strftime('%B %d, %Y')} as it's {holiday_name}. Please choose another date."
            }
        
        # Parse and validate time
        parsed_time = None
        time_formats = ['%I:%M %p', '%I %p', '%H:%M', '%I:%M%p', '%I%p']
        
        for fmt in time_formats:
            try:
                parsed_time = dt.strptime(preferred_time.upper(), fmt).time()
                break
            except ValueError:
                continue
        
        if not parsed_time:
            return {
                'available': False,
                'message': f"❌ I couldn't understand the time format '{preferred_time}'. Please use formats like '9:00 AM', '2:30 PM', or '14:30'."
            }
        
        # Check business hours (9:00 AM to 5:00 PM)
        business_start = dt.strptime('09:00', '%H:%M').time()
        business_end = dt.strptime('17:00', '%H:%M').time()
        
        if parsed_time < business_start or parsed_time > business_end:
            return {
                'available': False,
                'message': f"❌ Sorry, our business hours are 9:00 AM to 5:00 PM, Monday through Friday. The requested time {preferred_time} is outside our operating hours. Please choose a time between 9:00 AM and 5:00 PM."
            }
        
        return {
            'available': True,
            'validated_date': parsed_date.strftime('%Y-%m-%d'),
            'validated_time': parsed_time.strftime('%H:%M'),
            'message': 'Available'
        }
        
    except Exception as e:
        logger.error(f"Error validating appointment availability: {e}")
        return {
            'available': False,
            'message': f"❌ Error validating appointment time. Please try again with a clear date and time format."
        }

def extract_conversation_context(user_input):
    """Extract key context from user input to improve agent understanding"""
    context = {}
    
    # Extract pet names mentioned
    pet_names = ["chester", "misty", "snowball", "oliver", "luna"]
    mentioned_pets = [pet for pet in pet_names if pet.lower() in user_input.lower()]
    if mentioned_pets:
        context['pets'] = mentioned_pets
    
    # Extract action intent
    if any(word in user_input.lower() for word in ["change", "modify", "update", "reschedule"]):
        context['action'] = 'modify'
    elif any(word in user_input.lower() for word in ["book", "schedule", "appointment"]):
        context['action'] = 'schedule'
    elif any(word in user_input.lower() for word in ["cancel", "remove"]):
        context['action'] = 'cancel'
    
    # Extract service types
    services = ["grooming", "bath", "nail", "trim", "brush", "full grooming", "basic bath"]
    mentioned_services = [service for service in services if service in user_input.lower()]
    if mentioned_services:
        context['services'] = mentioned_services
    
    return context

def get_enhanced_memory_context(customer_id, query="recent conversations and preferences"):
    """Get enhanced memory context using semantic search"""
    global memory_tool_provider, memory_client, memory_id
    
    if not MEMORY_TOOLS_AVAILABLE or not memory_client or not memory_id:
        logger.debug("🔍 Enhanced memory tools not available, using basic retrieval")
        return None
    
    try:
        # Try to get memories from long-term memory strategies
        context_parts = []
        
        # 1. Get user preferences
        try:
            pref_namespace = f"/preferences/bella/{customer_id}"
            logger.debug(f"🔍 Searching preferences in namespace: {pref_namespace}")
            pref_memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=pref_namespace,
                query="grooming preferences and pet care patterns"
            )
            if pref_memories:
                context_parts.append("Customer Preferences:")
                for memory in pref_memories[:2]:
                    content = memory.get('content', '')
                    if content:
                        context_parts.append(f"- {content}")
                logger.debug(f"✅ Found {len(pref_memories)} preference memories")
        except Exception as e:
            logger.debug(f"Could not retrieve preferences: {e}")
        
        # 2. Get grooming knowledge/facts
        try:
            knowledge_namespace = f"/knowledge/bella/{customer_id}/grooming"
            logger.debug(f"🔍 Searching knowledge in namespace: {knowledge_namespace}")
            knowledge_memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=knowledge_namespace,
                query="pet grooming facts and service information"
            )
            if knowledge_memories:
                context_parts.append("Grooming Knowledge:")
                for memory in knowledge_memories[:2]:
                    content = memory.get('content', '')
                    if content:
                        context_parts.append(f"- {content}")
                logger.debug(f"✅ Found {len(knowledge_memories)} knowledge memories")
        except Exception as e:
            logger.debug(f"Could not retrieve knowledge: {e}")
        
        # 3. Get session summaries (try recent sessions)
        try:
            # Try to get summaries from recent sessions
            summary_namespace = f"/summaries/bella/{customer_id}"
            logger.debug(f"🔍 Searching summaries in namespace: {summary_namespace}")
            summary_memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=summary_namespace,
                query="recent grooming consultations and appointments"
            )
            if summary_memories:
                context_parts.append("Recent Session Summaries:")
                for memory in summary_memories[:2]:
                    content = memory.get('content', '')
                    if content:
                        context_parts.append(f"- {content}")
                logger.debug(f"✅ Found {len(summary_memories)} summary memories")
        except Exception as e:
            logger.debug(f"Could not retrieve summaries: {e}")
        
        if context_parts:
            context = "Long-term memory context:\n" + "\n".join(context_parts)
            logger.info(f"✅ Retrieved long-term memory context: {len(context)} characters")
            return context
        else:
            logger.debug("🔍 No long-term memories found, trying fallback approach...")
            
            # Fallback: Try broader namespaces
            for alt_namespace in [f"/preferences/bella/{customer_id}", f"/knowledge/bella/{customer_id}", f"/summaries/bella/{customer_id}"]:
                try:
                    alt_memories = memory_client.retrieve_memories(
                        memory_id=memory_id,
                        namespace=alt_namespace,
                        query=query
                    )
                    if alt_memories and len(alt_memories) > 0:
                        context = f"Memory context (from {alt_namespace}):\n"
                        for memory in alt_memories[:3]:
                            content = memory.get('content', '')
                            if content:
                                context += f"- {content}\n"
                        logger.info(f"✅ Retrieved {len(alt_memories)} memories from {alt_namespace}")
                        return context
                except Exception as alt_e:
                    logger.debug(f"Alternative namespace {alt_namespace} failed: {alt_e}")
                    continue
            
            logger.debug("🔍 No enhanced memories found in any namespace")
            return None
            
    except Exception as e:
        logger.debug(f"⚠️ Enhanced memory retrieval failed: {e}")
        return None

def get_conversation_context(customer_id, session_id):
    """Get recent conversation context from unified AgentCore Memory using get_last_k_turns"""
    global memory_client, memory_id
    
    # Ensure memory is initialized first
    if not memory_id or not memory_client:
        logger.debug("🔍 Memory not initialized, attempting to initialize...")
        initialize_memory(customer_id, session_id)
        
    if not memory_id or not memory_client:
        logger.debug("🔍 Memory not available - no context")
        return ""
    
    # Try enhanced memory first if available
    # enhanced_context = get_enhanced_memory_context(customer_id)
    # if enhanced_context:
    #     logger.info("✅ Using enhanced memory context")
    #     return enhanced_context
    
    try:
        # First, check if the session exists by listing events with a limit of 1
        logger.info(f"🔍 Checking if session {session_id} exists for customer {customer_id}...")
        session_exists = False
        try:
            events = memory_client.list_events(
                memory_id=memory_id,
                actor_id=customer_id,
                session_id=session_id
            )
            session_exists = len(events) > 0
            logger.info(f"✅ Session exists: {session_exists} (found {len(events)} events)")
        except Exception as e:
            logger.warning(f"⚠️ Error checking session existence: {e}")
            # Assume no events exist and continue
            session_exists = False
        
        # If session doesn't exist, no need to load conversation history
        if not session_exists:
            logger.info(f"📝 No existing conversation found for session {session_id}")
            return ""
        
        # Session exists, load the conversation history using get_last_k_turns
        logger.info(f"📚 Loading conversation history for existing session {session_id}")
        recent_turns = memory_client.get_last_k_turns(
            memory_id=memory_id,
            actor_id=customer_id,
            session_id=session_id,
            k=5  # Get last 5 conversation turns
        )
        
        if recent_turns:
            logger.info(f"✅ Loaded {len(recent_turns)} conversation turns from memory")
            context_messages = []
            
            for turn in recent_turns:
                for message in turn:
                    role = message.get('role', 'unknown')
                    content_obj = message.get('content', {})
                    
                    # Handle different content structures
                    if isinstance(content_obj, dict):
                        content = content_obj.get('text', '')
                    elif isinstance(content_obj, str):
                        content = content_obj
                    else:
                        content = str(content_obj)
                    
                    if content:
                        # Format role for display
                        display_role = "Customer" if role.lower() == 'user' else "Bella"
                        context_messages.append(f"{display_role}: {content}")
            
            if context_messages:
                context = "Recent conversation context:\n" + "\n".join(context_messages)
                logger.info(f"✅ Retrieved conversation context: {len(context)} characters")
                return context
            else:
                logger.debug("🔍 No conversation content found in turns")
        else:
            logger.info("📝 No recent turns found for this session")
        
    except Exception as e:
        logger.error(f"❌ Memory load error: {e}", exc_info=True)
        import traceback
        logger.error(f"🔍 Full traceback: {traceback.format_exc()}")
    
    return ""

# ============================================================================
# DYNAMODB HELPER FUNCTIONS
# ============================================================================

def get_customer_profile_with_logging(customer_id: str):
    """Get customer profile from auth table (EXACT same query as auth Lambda)"""
    try:
        logger.info("=" * 60)
        logger.info("�️ DoYNAMODB QUERY START - Customer Profile")
        logger.info("=" * 60)
        logger.info(f"🔑 Customer ID: {customer_id}")
        
        start_time = time.time()
        
        # Extract username from customer_id (same as auth Lambda)
        username = customer_id.replace('cust_', '') if customer_id.startswith('cust_') else customer_id
        logger.info(f"🔍 Looking up username: {username} in auth table")
        
        # Use DynamoDB resource (same as auth Lambda)
        table = dynamodb_resource.Table(TABLES['user_auth'])
        
        # EXACT same scan query as auth Lambda
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(username)
        )
        
        duration = time.time() - start_time
        logger.info(f"✅ DynamoDB query completed in {duration:.3f} seconds")
        
        items = response['Items']
        if not items:
            logger.warning(f"⚠️ No customer found with username: {username}")
            return None
        
        # Get first user (same as auth Lambda)
        user = items[0]
        logger.info(f"📊 Customer found in auth table: {len(user)} attributes")
        
        # Convert to decimal_to_native format (same as auth Lambda)
        user_data = decimal_to_native(dict(user))
        
        # Get pets data (EXACT same as auth Lambda)
        pets = user_data.get('pets', [])
        pets_count = len(pets) if pets else 0
        
        logger.info(f"👤 Customer Name: {user_data.get('name', 'N/A')}")
        logger.info(f"📧 Email: {user_data.get('email', 'N/A')}")
        logger.info(f"🐾 Pets Count: {pets_count}")
        logger.info("=" * 60)
        logger.info("✅ DYNAMODB QUERY SUCCESS - Customer Profile")
        logger.info("=" * 60)
        
        return user_data
            
    except Exception as e:
        logger.error("=" * 60)
        logger.error("❌ DYNAMODB QUERY FAILED - Customer Profile")
        logger.error("=" * 60)
        logger.error(f"❌ Error: {str(e)}")
        logger.error("=" * 60)
        return None

def save_appointment_with_logging(appointment_data):
    """Save appointment to DynamoDB with comprehensive logging"""
    try:
        logger.info("=" * 80)
        logger.info("💾 SAVING APPOINTMENT TO DYNAMODB")
        logger.info("=" * 80)
        logger.info(f"📋 Appointment Data: {json.dumps(appointment_data, default=str)}")
        
        start_time = time.time()
        
        # Use DynamoDB resource for saving
        appointments_table = dynamodb_resource.Table(TABLES['appointments'])
        
        # Prepare item for DynamoDB (convert to DynamoDB format)
        item = {
            'appointmentId': appointment_data['appointment_id'],
            'customerId': appointment_data['customer_id'],
            'customer_id': appointment_data['customer_id'],  # Both formats for compatibility
            'petName': appointment_data['pet_name'],
            'pet_name': appointment_data['pet_name'],  # Both formats for compatibility
            'serviceType': appointment_data['service_type'],
            'service': appointment_data['service_type'],  # Both formats for compatibility
            'appointmentDate': appointment_data['date'],
            'date': appointment_data['date'],  # Both formats for compatibility
            'appointmentTime': appointment_data['time'],
            'time': appointment_data['time'],  # Both formats for compatibility
            'cost': Decimal(str(appointment_data['cost'])),
            'duration': appointment_data['duration'],
            'notes': appointment_data['notes'],
            'status': 'Confirmed',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Save to DynamoDB
        response = appointments_table.put_item(Item=item)
        
        duration = time.time() - start_time
        logger.info(f"✅ Appointment saved successfully in {duration:.3f} seconds")
        logger.info(f"📊 HTTP Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode', 'Unknown')}")
        logger.info("=" * 80)
        logger.info("✅ APPOINTMENT SAVE COMPLETE")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ APPOINTMENT SAVE FAILED")
        logger.error("=" * 80)
        logger.error(f"❌ Error: {str(e)}")
        logger.error(f"📋 Failed appointment data: {json.dumps(appointment_data, default=str)}")
        logger.error("=" * 80)
        return False

def update_appointment_with_logging(appointment_id, updates):
    """Update existing appointment in DynamoDB"""
    try:
        logger.info("=" * 80)
        logger.info("🔄 UPDATING APPOINTMENT IN DYNAMODB")
        logger.info("=" * 80)
        logger.info(f"📋 Appointment ID: {appointment_id}")
        logger.info(f"📋 Updates: {json.dumps(updates, default=str)}")
        
        start_time = time.time()
        
        appointments_table = dynamodb_resource.Table(TABLES['appointments'])
        
        # Build update expression
        update_expression = "SET "
        expression_attribute_values = {}
        expression_attribute_names = {}
        
        for key, value in updates.items():
            attr_name = f"#{key}"
            attr_value = f":{key}"
            update_expression += f"{attr_name} = {attr_value}, "
            expression_attribute_names[attr_name] = key
            expression_attribute_values[attr_value] = value
        
        # Add updated_at timestamp
        update_expression += "#updated_at = :updated_at"
        expression_attribute_names["#updated_at"] = "updated_at"
        expression_attribute_values[":updated_at"] = datetime.now().isoformat()
        
        # Update the item
        response = appointments_table.update_item(
            Key={'appointmentId': appointment_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="UPDATED_NEW"
        )
        
        duration = time.time() - start_time
        logger.info(f"✅ Appointment updated successfully in {duration:.3f} seconds")
        logger.info(f"📊 HTTP Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode', 'Unknown')}")
        logger.info("=" * 80)
        logger.info("✅ APPOINTMENT UPDATE COMPLETE")
        logger.info("=" * 80)
        
        return True
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error("❌ APPOINTMENT UPDATE FAILED")
        logger.error("=" * 80)
        logger.error(f"❌ Error: {str(e)}")
        logger.error(f"📋 Failed appointment ID: {appointment_id}")
        logger.error("=" * 80)
        return False

def get_appointment_history_with_logging(customer_id: str, service_type: str = None):
    """Get appointment history (EXACT same logic as auth Lambda)"""
    try:
        logger.info(f"🔍 APPOINTMENT SEARCH for {customer_id}")
        
        # Use DynamoDB resource (same as auth Lambda)
        appointments_table = dynamodb_resource.Table(TABLES['appointments'])
        
        # EXACT same search logic as auth Lambda
        appointments = []
        username = customer_id.replace('cust_', '') if customer_id.startswith('cust_') else customer_id
        
        # Search by customerId
        try:
            response = appointments_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('customerId').eq(customer_id)
            )
            appointments.extend(response['Items'])
            logger.info(f"customerId search: {len(response['Items'])} appointments")
        except Exception as e:
            logger.warning(f"customerId search failed: {e}")
        
        # Search by customer_id (with underscore)
        try:
            response = appointments_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('customer_id').eq(customer_id)
            )
            appointments.extend(response['Items'])
            logger.info(f"customer_id search: {len(response['Items'])} appointments")
        except Exception as e:
            logger.warning(f"customer_id search failed: {e}")
        
        # Remove duplicates
        seen_ids = set()
        unique_appointments = []
        for apt in appointments:
            apt_id = apt.get('appointmentId', str(apt))
            if apt_id not in seen_ids:
                seen_ids.add(apt_id)
                unique_appointments.append(apt)
        
        logger.info(f"Found {len(unique_appointments)} appointments for {customer_id}")
        
        if unique_appointments:
            appointments_data = decimal_to_native(unique_appointments)
            
            # Return detailed appointment information
            appointment_details = []
            for apt in appointments_data:
                details = {
                    'id': apt.get('appointmentId', apt.get('appointment_id', 'N/A')),
                    'date': apt.get('appointmentDate', apt.get('date', 'N/A')),
                    'time': apt.get('appointmentTime', apt.get('time', 'N/A')),
                    'service': apt.get('serviceType', apt.get('service', 'N/A')),
                    'status': apt.get('status', 'N/A'),
                    'pet': apt.get('petName', apt.get('pet_name', 'N/A'))
                }
                appointment_details.append(details)
                logger.info(f"   📅 {details['date']} {details['time']} - {details['service']} for {details['pet']} ({details['status']})")
            
            return appointment_details
        else:
            logger.info("No appointments found")
            return None
            
    except Exception as e:
        logger.error(f"Appointment search error: {e}")
        return None

def save_appointment_with_logging(appointment_data):
    """Save appointment to DynamoDB"""
    try:
        start_time = time.time()
        
        # Prepare DynamoDB item (using correct key names to match existing table structure)
        dynamodb_item = {
            'appointmentId': {'S': appointment_data['appointment_id']},  # Fixed: use appointmentId not appointment_id
            'customer_id': {'S': appointment_data['customer_id']},
            'appointmentDate': {'S': appointment_data['date']},
            'appointmentTime': {'S': appointment_data['time']},
            'serviceType': {'S': appointment_data.get('service_type', 'grooming')},
            'agentType': {'S': 'bella'},
            'status': {'S': 'scheduled'},
            'cost': {'N': str(appointment_data['cost'])},
            'duration': {'N': str(appointment_data['duration'])},
            'notes': {'S': appointment_data['notes']},
            'petName': {'S': appointment_data['pet_name']},
            'createdAt': {'S': datetime.now().isoformat()}
        }
        
        log_dynamodb_request("PUT_ITEM", TABLES['appointments'], item=dynamodb_item)
        
        response = dynamodb.put_item(
            TableName=TABLES['appointments'],
            Item=dynamodb_item
        )
        
        duration = time.time() - start_time
        log_dynamodb_response("PUT_ITEM", response, duration)
        
        logger.info(f"✅ Appointment saved successfully: {appointment_data['appointment_id']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error saving appointment: {e}")
        return False

# ============================================================================
# STRANDS TOOLS - Complete implementation with all logic
# ============================================================================

@tool
def get_customer_and_pet_info(customer_id: str, pet_name: str = None):
    """Get customer and pet information from DynamoDB (EXACT same data as auth Lambda)"""
    try:
        customer = get_customer_profile_with_logging(customer_id)
        if not customer:
            return f"❌ Customer ID {customer_id} not found. Please verify the customer ID and try again."
        
        # Use native format (same as auth Lambda response)
        customer_info = f"""✅ Customer Information:
- Name: {customer.get('name', customer.get('full_name', 'Unknown'))}
- Email: {customer.get('email', '')}
- Phone: {customer.get('phone', '')}
- Membership: {customer.get('membership_level', 'Basic')}
- Total Appointments: {customer.get('appointments_count', 0)}"""

        # Get pets data (EXACT same as auth Lambda)
        pets = customer.get('pets', [])
        if pets:
            if pet_name:
                # Look for specific pet
                found_pet = next((pet for pet in pets if pet.get('name', '').lower() == pet_name.lower()), None)
                if found_pet:
                    pet_info = f"""

🐾 Pet Details:
- Name: {found_pet.get('name', 'Unknown')}
- Breed: {found_pet.get('breed', 'Unknown')}
- Species: {found_pet.get('species', 'Unknown')}
- Age: {found_pet.get('age', 'Unknown')} years
- Weight: {found_pet.get('weight', 'Unknown')} lbs"""
                    if found_pet.get('allergies'):
                        pet_info += f"\n- ⚠️ Allergies: {found_pet.get('allergies')}"
                else:
                    pet_info = f"\n\n❌ Pet '{pet_name}' not found for this customer."
            else:
                # List all pets
                pet_info = "\n\n🐾 Registered Pets:\n"
                for i, pet in enumerate(pets, 1):
                    pet_info += f"{i}. {pet.get('name', 'Unknown')} - {pet.get('breed', 'Unknown')} ({pet.get('species', 'Unknown')}, {pet.get('age', 'Unknown')} years, {pet.get('weight', 'Unknown')} lbs)\n"
                    if pet.get('allergies'):
                        pet_info += f"   ⚠️ Allergies: {pet.get('allergies')}\n"
        else:
            pet_info = "\n\n❌ No pets found for this customer."
        
        # Add appointment history (ALWAYS fetch fresh data from DynamoDB)
        appointments = get_appointment_history_with_logging(customer_id)
        if appointments:
            # Sort appointments by date to show most recent first
            try:
                appointments.sort(key=lambda x: (x.get('date', ''), x.get('time', '')), reverse=True)
            except:
                pass  # If sorting fails, use original order
                
            appointment_info = f"\n\n📅 All Appointments ({len(appointments)}):\n"
            for apt in appointments:  # Show ALL appointments, not just last 3
                appointment_info += f"- {apt['date']} at {apt['time']}: {apt['service']} for {apt['pet']} ({apt['status']})\n"
        else:
            appointment_info = "\n\n📅 No appointments found."
        
        return customer_info + pet_info + appointment_info
    except Exception as e:
        return f"❌ Error retrieving customer information: {str(e)}"

@tool
def grooming_services(pet_breed: str = None, pet_size: str = None):
    """Get available grooming services with detailed descriptions and breed-specific recommendations"""
    
    base_services = """🐾 **BELLA'S GROOMING SERVICES**

**1. Basic Bath Package** ($35-55)
- Gentle shampoo and conditioning
- Nail trimming and filing
- Ear cleaning and inspection
- Basic brushing and drying
- Cologne spritz

**2. Full Grooming Package** ($65-95)
- Everything in Basic Bath Package
- Professional haircut and styling
- Sanitary trim
- Paw pad trimming
- Teeth brushing
- Gland expression (if needed)

**3. Nail Care Service** ($20)
- Professional nail trimming
- Nail filing and smoothing
- Paw pad moisturizing

**4. Dental Care Package** ($30-40)
- Teeth brushing with pet-safe toothpaste
- Dental health assessment
- Breath freshening treatment

**5. De-shedding Treatment** ($45-65)
- Specialized de-shedding shampoo
- Professional brushing with de-shedding tools
- Undercoat removal
- Anti-shedding conditioning treatment

**6. Spa Package** ($85-120)
- All Full Grooming services
- Aromatherapy bath
- Moisturizing treatment
- Nail polish (optional)
- Bandana or bow tie
- Professional photo session"""

    breed_recommendations = ""
    if pet_breed:
        breed_lower = pet_breed.lower()
        if any(breed in breed_lower for breed in ['golden retriever', 'labrador', 'lab']):
            breed_recommendations = f"""

**🎯 SPECIAL RECOMMENDATIONS FOR {pet_breed.upper()}:**
- **Highly Recommended**: De-shedding Treatment (reduces shedding by 80%)
- **Best Value**: Full Grooming Package + De-shedding add-on
- **Frequency**: Every 6-8 weeks for optimal coat health
- **Special Care**: Double-coat requires professional undercoat removal"""
        
        elif any(breed in breed_lower for breed in ['poodle', 'doodle', 'goldendoodle', 'labradoodle']):
            breed_recommendations = f"""

**🎯 SPECIAL RECOMMENDATIONS FOR {pet_breed.upper()}:**
- **Essential**: Full Grooming Package (prevents matting)
- **Frequency**: Every 4-6 weeks to maintain coat
- **Special Care**: Professional scissoring and clipper work required
- **Add-on**: Face and feet trimming between full grooms"""
        
        elif any(breed in breed_lower for breed in ['german shepherd', 'husky', 'malamute']):
            breed_recommendations = f"""

**🎯 SPECIAL RECOMMENDATIONS FOR {pet_breed.upper()}:**
- **Must-Have**: De-shedding Treatment (essential for double coats)
- **Seasonal**: Extra de-shedding during spring and fall
- **Frequency**: Every 8-10 weeks, more during shedding season
- **Special Care**: Never shave - damages double coat permanently"""

    size_pricing = ""
    if pet_size:
        size_lower = pet_size.lower()
        if size_lower in ['small', 'toy']:
            size_pricing = f"""

**💰 PRICING FOR {pet_size.upper()} DOGS:**
- Basic Bath: $35-40
- Full Grooming: $65-75
- De-shedding: $45-50
- Spa Package: $85-95"""
        elif size_lower in ['medium']:
            size_pricing = f"""

**💰 PRICING FOR {pet_size.upper()} DOGS:**
- Basic Bath: $40-45
- Full Grooming: $75-85
- De-shedding: $50-60
- Spa Package: $95-110"""
        elif size_lower in ['large', 'extra large', 'xl']:
            size_pricing = f"""

**💰 PRICING FOR {pet_size.upper()} DOGS:**
- Basic Bath: $45-55
- Full Grooming: $85-95
- De-shedding: $60-65
- Spa Package: $110-120"""

    return base_services + breed_recommendations + size_pricing

@tool
def modify_grooming_appointment(customer_id: str, pet_name: str, old_date: str, new_date: str, new_time: str = None, new_service: str = None):
    """Modify an existing grooming appointment - requires explicit time confirmation"""
    try:
        logger.info(f"🔄 Modifying appointment for {customer_id}, pet: {pet_name}")
        
        # Find the existing appointment
        appointments = get_appointment_history_with_logging(customer_id)
        if not appointments:
            return f"❌ No appointments found for customer {customer_id}."
        
        # Find appointments for this pet on the old date
        matching_appointments = []
        for apt in appointments:
            if apt['pet'].lower() == pet_name.lower() and old_date in apt['date']:
                matching_appointments.append(apt)
        
        if not matching_appointments:
            return f"❌ No appointment found for {pet_name} on {old_date}."
        
        # If multiple appointments, ask for clarification
        if len(matching_appointments) > 1 and not new_time:
            apt_list = "\n".join([f"- {apt['time']} - {apt['service']}" for apt in matching_appointments])
            return f"""I found multiple appointments for {pet_name} on {old_date}:
{apt_list}

Please specify which appointment you want to change by providing the time, or tell me the new time you prefer."""
        
        # Use the first/only appointment
        target_appointment = matching_appointments[0]
        
        # If no new time specified, ask for it
        if not new_time:
            return f"""I found {pet_name}'s appointment on {old_date} at {target_appointment['time']} for {target_appointment['service']}.

To reschedule it to {new_date}, what time would you prefer? 

Please note our business hours are 9:00 AM to 5:00 PM, Monday through Friday. We're closed on weekends and US federal holidays."""
        
        # Validate the new date and time
        availability_check = validate_appointment_availability(new_date, new_time)
        if not availability_check['available']:
            return availability_check['message']
        
        # Use validated date and time
        new_date = availability_check['validated_date']
        new_time = availability_check['validated_time']
        
        # Prepare updates
        updates = {
            'appointmentDate': new_date,
            'date': new_date  # Both formats for compatibility
        }
        
        if new_time:
            updates['appointmentTime'] = new_time
            updates['time'] = new_time
        
        if new_service:
            updates['serviceType'] = new_service
            updates['service'] = new_service
        
        # Update the appointment
        if update_appointment_with_logging(target_appointment['id'], updates):
            return f"""✅ **APPOINTMENT SUCCESSFULLY RESCHEDULED!**

📅 **Updated Appointment Details:**
- Pet: {pet_name}
- OLD: {old_date} at {target_appointment['time']}
- NEW: {new_date} at {new_time or target_appointment['time']}
- Service: {new_service or target_appointment['service']}
- Status: Confirmed

The appointment has been updated in our database. You'll receive a confirmation email shortly."""
        else:
            return f"❌ Failed to update the appointment. Please try again or contact support."
        
    except Exception as e:
        logger.error(f"Error modifying appointment: {e}")
        return f"❌ Error modifying appointment: {str(e)}"

@tool
def schedule_grooming_appointment(customer_id: str, pet_name: str, service_type: str, preferred_date: str, preferred_time: str, special_notes: str = ""):
    """Schedule a grooming appointment with availability checking"""
    try:
        logger.info(f"🗓️ Scheduling appointment for {customer_id}, pet: {pet_name}")
        
        # Verify customer and pet exist
        customer = get_customer_profile_with_logging(customer_id)
        if not customer:
            return f"❌ Customer ID {customer_id} not found. Please verify the customer ID."
        
        pets = customer.get('pets', [])
        found_pet = next((pet for pet in pets if pet.get('name', '').lower() == pet_name.lower()), None)
        if not found_pet:
            return f"❌ Pet '{pet_name}' not found for customer {customer_id}."
        
        # Generate appointment ID
        appointment_id = f"BELLA_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        
        # Validate business hours and availability
        availability_check = validate_appointment_availability(preferred_date, preferred_time)
        if not availability_check['available']:
            return availability_check['message']
        
        # Use the validated date and time
        preferred_date = availability_check['validated_date']
        preferred_time = availability_check['validated_time']
        
        # Determine service cost and duration
        service_costs = {
            'basic bath': {'cost': 45, 'duration': 60},
            'full grooming': {'cost': 80, 'duration': 120},
            'nail care': {'cost': 20, 'duration': 30},
            'dental care': {'cost': 35, 'duration': 45},
            'de-shedding': {'cost': 55, 'duration': 90},
            'spa package': {'cost': 100, 'duration': 150}
        }
        
        service_key = service_type.lower()
        service_info = service_costs.get(service_key, {'cost': 50, 'duration': 60})
        
        # Create appointment data
        appointment_data = {
            'appointment_id': appointment_id,
            'customer_id': customer_id,
            'pet_name': pet_name,
            'service_type': service_type,
            'date': preferred_date,
            'time': preferred_time,
            'cost': service_info['cost'],
            'duration': service_info['duration'],
            'notes': special_notes or f"Grooming appointment for {pet_name} - {service_type}"
        }
        
        # Save appointment
        if save_appointment_with_logging(appointment_data):
            return f"""✅ **APPOINTMENT CONFIRMED!**

📅 **Appointment Details:**
- Appointment ID: {appointment_id}
- Customer: {customer.get('name', customer_id)}
- Pet: {pet_name} ({found_pet.get('breed', 'Unknown breed')})
- Service: {service_type}
- Date: {preferred_date}
- Time: {preferred_time}
- Duration: {service_info['duration']} minutes
- Cost: ${service_info['cost']}
- Status: Confirmed

📞 **Next Steps:**
1. You'll receive a confirmation email shortly
2. Please arrive 10 minutes early
3. Bring your pet's vaccination records if this is your first visit
4. Call us at (555) 123-PETS if you need to reschedule

💡 **Preparation Tips:**
- Give your pet a light meal 2 hours before the appointment
- Bring their favorite toy for comfort
- Let us know about any behavioral concerns

Thank you for choosing Bella's Grooming! We look forward to pampering {pet_name}! 🐾"""
        else:
            return f"❌ I encountered an error while saving your appointment. Please try again or contact our support team."
        
    except Exception as e:
        logger.error(f"Error scheduling appointment: {e}")
        return f"❌ I encountered an error while scheduling your appointment: {str(e)}. Please try again or contact our support team."

@tool
def list_customer_appointments(customer_id: str):
    """List ALL appointments for a customer - always fetches fresh data from DynamoDB with duplicate detection"""
    try:
        logger.info(f"🔍 Fetching fresh appointment data for customer: {customer_id}")
        
        # Always fetch fresh data from DynamoDB
        appointments = get_appointment_history_with_logging(customer_id)
        
        if not appointments:
            return "📅 No appointments found for this customer."
        
        # Detect and flag duplicates
        duplicates = []
        unique_appointments = []
        seen_combinations = set()
        
        for apt in appointments:
            # Create a key for duplicate detection (pet, date, time, service)
            key = (apt['pet'].lower(), apt['date'], apt['time'], apt['service'].lower())
            if key in seen_combinations:
                duplicates.append(apt)
            else:
                seen_combinations.add(key)
                unique_appointments.append(apt)
        
        # Sort appointments by date and time
        try:
            unique_appointments.sort(key=lambda x: (x.get('date', ''), x.get('time', '')))
        except:
            pass  # If sorting fails, just use the original order
        
        appointment_list = f"📅 **ALL APPOINTMENTS FOR CUSTOMER** ({len(unique_appointments)} unique"
        if duplicates:
            appointment_list += f", {len(duplicates)} duplicates detected"
        appointment_list += "):\n\n"
        
        for i, apt in enumerate(unique_appointments, 1):
            appointment_list += f"{i}. **{apt['date']} at {apt['time']}**\n"
            appointment_list += f"   - Service: {apt['service']}\n"
            appointment_list += f"   - Pet: {apt['pet']}\n"
            appointment_list += f"   - Status: {apt['status']}\n"
            appointment_list += f"   - ID: {apt['id']}\n\n"
        
        # Add duplicate warning if found
        if duplicates:
            appointment_list += f"⚠️ **DUPLICATE APPOINTMENTS DETECTED** ({len(duplicates)}):\n"
            for dup in duplicates:
                appointment_list += f"- DUPLICATE: {dup['date']} at {dup['time']} - {dup['service']} for {dup['pet']} (ID: {dup['id']})\n"
            appointment_list += "\nWould you like me to help remove these duplicate appointments?\n"
        
        return appointment_list
        
    except Exception as e:
        logger.error(f"Error listing appointments: {e}")
        return f"❌ Error retrieving appointments: {str(e)}"

@tool
def get_memory_context(customer_id: str, session_id: str = None):
    """Get conversation context from AgentCore Memory"""
    try:
        # Initialize memory if not already done
        if not memory_id:
            initialize_memory(customer_id, session_id)
        
        context = get_conversation_context(customer_id, session_id or "default")
        
        if context:
            return f"📝 **Previous Conversation Context:**\n{context}"
        else:
            return "📝 No previous conversation history found."
            
    except Exception as e:
        logger.error(f"Error getting memory context: {e}")
        return "📝 Unable to retrieve conversation history at this time."

@tool
def save_conversation_memory(customer_id: str, user_message: str, bella_response: str, session_id: str = None):
    """Save current conversation to AgentCore Memory"""
    try:
        # Initialize memory if not already done
        if not memory_id:
            initialize_memory(customer_id, session_id)
        
        save_conversation_to_memory(customer_id, session_id or "default", user_message, bella_response)
        return "✅ Conversation saved to memory successfully."
        
    except Exception as e:
        logger.error(f"Error saving to memory: {e}")
        return "⚠️ Unable to save conversation to memory."

# ============================================================================
# STRANDS AGENT SETUP - Following working pattern
# ============================================================================

# Create Bedrock model
model = BedrockModel(
    model_id=MODEL_ID,
)

# Create base tools list (preserving all existing logic)
base_tools = [
    get_customer_and_pet_info,
    grooming_services,
    schedule_grooming_appointment,
    modify_grooming_appointment,
    list_customer_appointments,
    get_memory_context,
    save_conversation_memory
]

# Create Strands agent with all tools (enhanced with memory tools when available)
agent = Agent(
    model=model,
    tools=base_tools,
    system_prompt="""You are Bella, a professional pet grooming specialist at GenAI Pet Store.

CRITICAL: You MUST use your tools to provide accurate information. Never guess or make up information.

🔧 **MANDATORY Tool Usage Rules:**
1. When a customer provides a customer ID or asks about their pets/appointments, ALWAYS use get_customer_and_pet_info tool FIRST
2. When asked about services, pricing, or packages, ALWAYS use grooming_services tool
3. When asked to schedule, book, or make appointments, ALWAYS use schedule_grooming_appointment tool
4. NEVER provide customer or pet information without using the tools first

🐾 **Your Available Tools:**
- get_customer_and_pet_info(customer_id, pet_name=None): Look up customer and pet data from our database
- grooming_services(pet_breed=None, pet_size=None): Get current service offerings and pricing
- schedule_grooming_appointment(customer_id, pet_name, service_type, preferred_date, preferred_time, special_notes=""): Book NEW appointments
- modify_grooming_appointment(customer_id, pet_name, old_date, new_date, new_time=None, new_service=None): MODIFY existing appointments
- list_customer_appointments(customer_id): Get fresh appointment data from database
- get_memory_context(customer_id, session_id=None): Retrieve conversation history
- save_conversation_memory(customer_id, user_message, bella_response, session_id=None): Save conversation context

🎯 **Critical Response Patterns:**
1. Customer asks about pets/info → IMMEDIATELY use get_customer_and_pet_info tool
2. Customer asks about services/pricing → IMMEDIATELY use grooming_services tool
3. Customer wants to book/schedule → IMMEDIATELY use schedule_grooming_appointment tool
4. Customer says "appointment", "schedule", "book" → Use schedule_grooming_appointment tool

🚨 **CONTEXT UNDERSTANDING RULES:**
- When customer says "change Snowball's appointment" → They want to MODIFY an existing appointment for pet named Snowball
- When customer says "book appointment for Chester" → They want to SCHEDULE a new appointment for pet named Chester
- When customer mentions a specific pet name, remember it for the entire conversation
- When customer says "change" or "modify" → Use modify_grooming_appointment tool, NOT schedule_grooming_appointment
- When customer provides specific details (pet name, service type, date), don't ask for them again

🚨 **APPOINTMENT MANAGEMENT REQUIREMENTS:**
- For NEW appointments: Use schedule_grooming_appointment tool
- For CHANGING/MODIFYING appointments: Use modify_grooming_appointment tool
- For LISTING appointments: Use list_customer_appointments tool to get fresh data from database
- When customer says "change Nov 11 to Nov 14": ALWAYS ask for preferred time before calling modify_grooming_appointment
- NEVER assume appointment times - always ask the customer for their preferred time
- When scheduling new appointments, ensure dates are in 2025 or later (never past dates)
- ALWAYS use the database tools - never rely only on memory for appointment data
- After modifying appointments, confirm the change was saved to the database

🕒 **BUSINESS HOURS & AVAILABILITY:**
- Business Hours: 9:00 AM to 5:00 PM, Monday through Friday ONLY
- CLOSED: Saturdays, Sundays, and US federal holidays
- If customer requests weekend/holiday/outside hours: Politely decline and suggest alternative times
- When customer doesn't specify time, suggest: "What time would you prefer? Our hours are 9:00 AM to 5:00 PM, Monday-Friday."

Be warm and professional, but ALWAYS use the appropriate tools for each request. Pay attention to context and don't repeat questions when the customer has already provided 
the information."""
)

@app.entrypoint
def bella_grooming_agent(payload, context):
    """
    Bella Grooming Agent with complete memory, session, and DynamoDB integration
    """
    try:
        user_input = payload.get("prompt", "Hello! How can I help you today?")
        customer_id = payload.get("customer_id", "")
        session_id = context.session_id or ""
        
        logger.info(f"🐾 Bella Agent - Processing request for customer: {customer_id}")
        logger.info(f"🔗 Session ID: {session_id}")
        
        # Extract context from user input to improve understanding
        conversation_context = extract_conversation_context(user_input)
        if conversation_context:
            logger.info(f"🧠 Extracted context: {conversation_context}")
        
        # Initialize unified memory for this customer/session
        current_agent = agent  # Use the global agent by default
        
        if customer_id or session_id:
            initialize_memory(customer_id, session_id)
            logger.info(f"🧠 Using unified memory with actor_id={customer_id}, session_id={session_id}")
            
            # Also initialize enhanced memory tools if available
            if MEMORY_TOOLS_AVAILABLE and customer_id:
                memory_provider = initialize_memory_tools(customer_id, session_id)
                # Enhance agent with memory tools for this session (non-destructive)
                if memory_provider and hasattr(memory_provider, 'tools'):
                    try:
                        # Create enhanced agent with memory tools for this conversation
                        enhanced_tools = base_tools + memory_provider.tools
                        current_agent = Agent(model=model, tools=enhanced_tools)
                        logger.info(f"✅ Enhanced agent with {len(memory_provider.tools)} memory tools using unified memory")
                    except Exception as e:
                        logger.warning(f"Could not enhance agent with memory tools: {e}")
                        # Continue with base agent (preserving existing functionality)
        
        # Get conversation context if available
        context = ""
        if customer_id:
            try:
                context = get_conversation_context(customer_id, session_id)
                if context:
                    logger.info(f"🧠 Retrieved conversation context: {len(context)} characters")
            except Exception as e:
                logger.warning(f"Could not retrieve context: {e}")
        
        # Let Strands agent handle tool selection naturally with enhanced context
        enhanced_input = user_input
        
        # Add customer context if available
        if customer_id:
            enhanced_input = f"Customer ID: {customer_id}\n\n{user_input}"

        
        # Add conversation context if available
        if context:
            enhanced_input = f"Previous conversation context:\n{context}\n\nCurrent request: {enhanced_input}"

        
        # Let Strands agent decide which tools to use

        response = current_agent(enhanced_input)
        
        # Handle different response structures safely
        try:
            if hasattr(response, 'message') and response.message:
                if isinstance(response.message, dict) and 'content' in response.message:
                    content = response.message['content']
                    if isinstance(content, list) and len(content) > 0:
                        # Safely access the first content item
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
                # Try common dict keys
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
        if customer_id:
            try:
                save_conversation_to_memory(customer_id, session_id or "default", user_input, result)

            except Exception as e:
                logger.warning(f"Could not save to memory: {e}")
        

        return result
        
    except Exception as e:
        logger.error(f"❌ Error in Bella agent: {e}")
        return f"I apologize, but I encountered an error: {str(e)}. Please try again or contact support."

if __name__ == "__main__":
    app.run()