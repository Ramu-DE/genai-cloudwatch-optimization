#!/usr/bin/env python3
"""
Luna Nutrition Agent - Complete Implementation with Memory & Session Management
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

# Configure logging (reduced verbosity for production)
log_file = os.path.join(os.path.expanduser('~'), 'luna_agent.log')
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

logger.info("🥗 LUNA NUTRITION AGENT STARTING UP - FULL IMPLEMENTATION")
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
    """Initialize AgentCore Memory with customer-specific ID"""
    global memory_client, memory_id
    
    if not MEMORY_AVAILABLE:
        logger.warning("⚠️ AgentCore Memory not available - using basic conversation tracking")
        return None
    
    # Create customer-specific memory ID
    if customer_id:
        target_memory_id = f"LunaNutrition_Customer_{customer_id}"
    elif session_id and 'cust_' in session_id:
        cust_part = session_id.split('cust_')[1].split('-')[0] if 'cust_' in session_id else None
        target_memory_id = f"LunaNutrition_Customer_{cust_part}" if cust_part else f"LunaNutrition_Session_{session_id[:20]}"
    else:
        target_memory_id = f"LunaNutrition_Session_{session_id[:20] if session_id else 'default'}"
    
    # Check if we already have a memory_id for this customer
    if memory_id:
        logger.info(f"🧠 Using cached memory ID for luna/{customer_id}")
        return memory_id
    
    try:
        logger.info("🧠 Initializing AgentCore Memory with long-term strategies...")
        memory_client = MemoryClient(region_name=AWS_REGION)
        
        # FIRST: List all existing memories and try to find a match
        try:
            memories = memory_client.list_memories()
            
            # Look for memory with matching name (name is embedded in the ID)
            existing_memory = None
            for m in memories:
                memory_id_field = m.get('id')  # This is the actual memory ID
                
                # Check if our target memory name is part of the memory ID
                if memory_id_field and target_memory_id in memory_id_field:
                    existing_memory = m
                    break
            
            if existing_memory:
                # Get the memory ID from the found memory (use 'id' field as per documentation)
                memory_id = existing_memory.get('id')
                logger.info(f"✅ Found existing memory: {memory_id}")
                return memory_id
                
        except Exception as e:
            logger.warning(f"Error listing memories: {e}")
        
        # SECOND: Try to create new memory only if none exists
        try:
            memory = memory_client.create_memory_and_wait(
                name=target_memory_id,
                description="Persistent memory for Luna nutrition agent with long-term retention",
                strategies=[
                    {
                        "summaryMemoryStrategy": {
                            "name": "NutritionSessionSummarizer",
                            "description": "Summarizes nutrition consultations and dietary recommendations",
                            "namespaces": ["/summaries/luna/{actorId}/{sessionId}"]
                        }
                    },
                    {
                        "semanticMemoryStrategy": {
                            "name": "NutritionKnowledgeBase",
                            "description": "Stores nutrition facts, dietary knowledge, and feeding information",
                            "namespaces": ["/knowledge/luna/{actorId}/nutrition"]
                        }
                    },
                    {
                        "userPreferenceMemoryStrategy": {
                            "name": "DietaryPreferences",
                            "description": "Learns customer dietary preferences and pet nutrition patterns",
                            "namespaces": ["/preferences/luna/{actorId}"]
                        }
                    }
                ],
                event_expiry_days=20
            )
            
            memory_id = memory.get('id') or memory.get('memoryId')
            logger.info(f"✅ Memory created: {memory_id}")
            return memory_id
            
        except Exception as create_error:
            logger.error(f"Failed to create memory: {create_error}")
            
            # THIRD: If creation failed because it exists, try to find it again
            if "already exists" in str(create_error):
                try:
                    memories = memory_client.list_memories()
                    for m in memories:
                        memory_id_field = m.get('id')
                        if memory_id_field and target_memory_id in memory_id_field:
                            memory_id = memory_id_field
                            logger.info(f"✅ Found existing memory: {memory_id}")
                            return memory_id
                    
                    logger.error(f"Could not find existing memory with name: {target_memory_id}")
                except Exception as find_error:
                    logger.error(f"Error in memory search: {find_error}")
            
            logger.error(f"⚠️ Could not set up AgentCore Memory: {create_error}")
            return None
        
    except Exception as e:
        logger.error(f"⚠️ Could not set up AgentCore Memory: {e}")
        memory_id = None
        return None

def initialize_memory_tools(customer_id, session_id=None):
    """Initialize AgentCore Memory Tool Provider for enhanced memory capabilities"""
    global memory_tool_provider, memory_id
    
    if not MEMORY_TOOLS_AVAILABLE or not memory_id:
        logger.info("⚠️ Memory tools not available or memory not initialized")
        return None
    
    try:
        # Create namespace for this customer (align with long-term memory strategies)
        namespace = f"/preferences/luna/{customer_id}"
        
        memory_tool_provider = AgentCoreMemoryToolProvider(
            memory_id=memory_id,
            actor_id=customer_id,
            session_id=session_id or "default",
            namespace=namespace,
            region=AWS_REGION
        )
        
        logger.info(f"✅ Memory tool provider initialized for customer {customer_id}")
        logger.info(f"🗂️ Using namespace: {namespace}")
        return memory_tool_provider
        
    except Exception as e:
        logger.error(f"⚠️ Could not initialize memory tool provider: {e}")
        return None

def save_conversation_to_memory(customer_id, session_id, user_message, luna_response):
    """Save conversation turn to AgentCore Memory with length management"""
    global memory_client, memory_id
    
    if not memory_id or not memory_client:
        logger.debug("💾 Memory not available - skipping save")
        return
    
    try:
        logger.info(f"💾 Saving to memory: User='{user_message[:30]}...', Luna='{luna_response[:30]}...'")
        
        # Truncate messages if they exceed AgentCore's 9000 character limit
        max_length = 8500  # Leave buffer for metadata
        
        truncated_user_message = user_message
        if len(user_message) > max_length:
            truncated_user_message = user_message[:max_length] + "... [truncated]"
            logger.warning(f"⚠️ User message truncated from {len(user_message)} to {len(truncated_user_message)} chars")
        
        truncated_luna_response = luna_response
        if len(luna_response) > max_length:
            # Intelligent truncation - keep beginning and end
            half_length = max_length // 2
            truncated_luna_response = (
                luna_response[:half_length] + 
                "... [middle truncated] ..." + 
                luna_response[-half_length:]
            )
            logger.warning(f"⚠️ Luna response truncated from {len(luna_response)} to {len(truncated_luna_response)} chars")
        
        # Save to customer-specific memory (session ID can vary)
        memory_client.create_event(
            memory_id=memory_id,
            actor_id=customer_id,
            session_id=session_id,  # Use actual session ID for this conversation
            messages=[
                (truncated_user_message, "user"),
                (truncated_luna_response, "assistant")
            ]
        )
        logger.info("✅ Successfully saved to memory")
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
    services = ["nutrition", "diet", "dietary", "consultation", "weight management", "allergy", "senior nutrition", "performance nutrition"]
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
            pref_namespace = f"/preferences/luna/{customer_id}"
            logger.debug(f"🔍 Searching preferences in namespace: {pref_namespace}")
            pref_memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=pref_namespace,
query="nutrition preferences and dietary patterns"
            )
            if pref_memories:
                context_parts.append("Dietary Preferences:")
                for memory in pref_memories[:2]:
                    content = memory.get('content', '')
                    if content:
                        context_parts.append(f"- {content}")
                logger.debug(f"✅ Found {len(pref_memories)} dietary preference memories")
        except Exception as e:
            logger.debug(f"Could not retrieve preferences: {e}")
        
        # 2. Get nutrition knowledge/facts
        try:
            knowledge_namespace = f"/knowledge/luna/{customer_id}/nutrition"
            logger.debug(f"🔍 Searching knowledge in namespace: {knowledge_namespace}")
            knowledge_memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=knowledge_namespace,
                query="pet nutrition facts and dietary information"
            )
            if knowledge_memories:
                context_parts.append("Nutrition Knowledge:")
                for memory in knowledge_memories[:2]:
                    content = memory.get('content', '')
                    if content:
                        context_parts.append(f"- {content}")
                logger.debug(f"✅ Found {len(knowledge_memories)} nutrition knowledge memories")
        except Exception as e:
            logger.debug(f"Could not retrieve knowledge: {e}")
        
        # 3. Get session summaries (try recent sessions)
        try:
            # Try to get summaries from recent sessions
            summary_namespace = f"/summaries/luna/{customer_id}"
            logger.debug(f"🔍 Searching summaries in namespace: {summary_namespace}")
            summary_memories = memory_client.retrieve_memories(
                memory_id=memory_id,
                namespace=summary_namespace,
                query="recent nutrition consultations and dietary assessments"
            )
            if summary_memories:
                context_parts.append("Recent Nutrition Consultations:")
                for memory in summary_memories[:2]:
                    content = memory.get('content', '')
                    if content:
                        context_parts.append(f"- {content}")
                logger.debug(f"✅ Found {len(summary_memories)} consultation summaries")
        except Exception as e:
            logger.debug(f"Could not retrieve summaries: {e}")
        
        if context_parts:
            context = "Long-term nutrition memory context:\n" + "\n".join(context_parts)
            logger.info(f"✅ Retrieved long-term nutrition memory context: {len(context)} characters")
            return context
        else:
            logger.debug("🔍 No long-term memories found, trying fallback approach...")
            
            # Fallback: Try broader namespaces
            for alt_namespace in [f"/preferences/luna/{customer_id}", f"/knowledge/luna/{customer_id}", f"/summaries/luna/{customer_id}"]:
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
    """Get recent conversation context from AgentCore Memory (preserving existing logic)"""
    global memory_client, memory_id
    
    # Ensure memory is initialized first
    if not memory_id or not memory_client:
        logger.debug("🔍 Memory not initialized, attempting to initialize...")
        initialize_memory(customer_id, session_id)
        
    if not memory_id or not memory_client:
        logger.debug("🔍 Memory not available - no context")
        return ""
    
    # Try enhanced memory first if available
    enhanced_context = get_enhanced_memory_context(customer_id)
    if enhanced_context:
        logger.info("✅ Using enhanced memory context")
        return enhanced_context
    
    try:
        # Get recent conversation events for this customer across ALL sessions
        # Since session_id is required, we'll use the current session but also try to get more data
        logger.debug(f"🔍 Searching for events: memory_id={memory_id}, actor_id={customer_id}")
        
        # Try to get events - first attempt with current session
        all_events = []
        try:
            current_events = memory_client.list_events(
                memory_id=memory_id,
                actor_id=customer_id,
                session_id=session_id or "default",
                max_results=20
            )
            all_events.extend(current_events)
            logger.debug(f"🔍 Found {len(current_events)} events in current session")
        except Exception as e:
            logger.debug(f"🔍 Could not get current session events: {e}")
        
        # Try without session_id if the API supports it
        try:
            # Some AgentCore APIs might support getting all events for an actor
            all_actor_events = memory_client.list_events(
                memory_id=memory_id,
                actor_id=customer_id,
                max_results=30  # Get more since we're looking across all sessions
            )
            # Add events that aren't already in our list
            for event in all_actor_events:
                if event not in all_events:
                    all_events.append(event)
            logger.debug(f"🔍 Found {len(all_actor_events)} total events for actor")
        except Exception as e:
            logger.debug(f"🔍 Could not get all actor events (API might not support it): {e}")
        
        logger.debug(f"🔍 Found {len(all_events) if all_events else 0} events for customer {customer_id} in session {session_id or 'default'}")
        
        # Try to get events from other session patterns to simulate cross-session
        logger.debug("🔍 Trying to find events from other sessions...")
        session_patterns_to_try = [
            "default", 
            "chat-session",
            "",
            # Try some recent session patterns that might exist
            f"chat-session-{customer_id}",
            f"session-{customer_id}",
        ]
        
        # Also try to find events by using a broader search approach
        for alt_session in session_patterns_to_try:
            if alt_session != (session_id or "default"):
                try:
                    alt_events = memory_client.list_events(
                        memory_id=memory_id,
                        actor_id=customer_id,
                        session_id=alt_session,
                        max_results=10
                    )
                    if alt_events:
                        all_events.extend(alt_events)
                        logger.debug(f"🔍 Found {len(alt_events)} additional events in session '{alt_session}'")
                except Exception as e:
                    logger.debug(f"🔍 Could not get events from session '{alt_session}': {e}")
                    continue
        
        # If still no events, try a different approach - use a wildcard-like session search
        if len(all_events) == 0:
            logger.debug("🔍 Still no events found, trying wildcard session approach...")
            try:
                # Try with a very generic session ID that might capture more events
                for generic_session in ["*", "chat-session-*", "session-*"]:
                    try:
                        generic_events = memory_client.list_events(
                            memory_id=memory_id,
                            actor_id=customer_id,
                            session_id=generic_session,
                            max_results=15
                        )
                        if generic_events:
                            all_events.extend(generic_events)
                            logger.debug(f"🔍 Found {len(generic_events)} events with generic session '{generic_session}'")
                            break
                    except Exception as e:
                        logger.debug(f"🔍 Generic session '{generic_session}' failed: {e}")
                        continue
            except Exception as e:
                logger.debug(f"🔍 Wildcard session search failed: {e}")
        
        # If we have events, build context from the most recent ones
        if all_events:
            # Sort events by timestamp to get the most recent ones
            try:
                all_events.sort(key=lambda x: x.get('eventTimestamp', ''), reverse=True)
            except:
                pass  # If sorting fails, use events as-is
            
            context = "Recent conversation context:\n"
            for event in all_events[:6]:  # Get last 6 events (3 turns typically)
                # Each event has a payload with conversational messages
                if 'payload' in event:
                    for payload_item in event['payload']:
                        if 'conversational' in payload_item:
                            conv = payload_item['conversational']
                            role = "Customer" if conv.get('role', '').lower() == 'user' else "Luna"
                            content = conv.get('content', {}).get('text', '')
                            if content:
                                context += f"{role}: {content}\n"
            
            if len(context) > len("Recent conversation context:\n"):
                logger.info(f"✅ Retrieved conversation context: {len(context)} characters")
                return context
            else:
                logger.debug("🔍 No conversation content found in events")
        else:
            logger.debug("🔍 No events found for this customer")
            
            # Debug: Try to list ALL events in the memory to see if there's anything
            try:
                all_memory_events = memory_client.list_events(
                    memory_id=memory_id,
                    max_results=5  # Just a few to see if memory has any data
                )
                logger.debug(f"🔍 Total events in memory: {len(all_memory_events) if all_memory_events else 0}")
                if all_memory_events:
                    for i, event in enumerate(all_memory_events[:2]):
                        logger.debug(f"🔍 Sample event {i}: actor_id={event.get('actorId', 'N/A')}")
            except Exception as debug_e:
                logger.debug(f"🔍 Could not list all events for debugging: {debug_e}")
            
    except Exception as e:
        logger.error(f"⚠️ Could not retrieve context from memory: {e}")
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
            'appointmentTime': {'S': appointment_data.get('time', appointment_data.get('appointment_time', '10:00 AM'))},
            'serviceType': {'S': appointment_data.get('service_type', 'nutrition consultation')},
            'agentType': {'S': 'luna'},
            'status': {'S': 'scheduled'},
            'cost': {'N': str(appointment_data.get('cost', 0))},
            'duration': {'N': str(appointment_data.get('duration', 60))},
            'notes': {'S': appointment_data.get('notes', '')},
            'petName': {'S': appointment_data.get('pet_name', '')},
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
def nutrition_services():
    """Get available nutrition services with detailed descriptions"""
    return """🥗 Available Nutrition Services:

🔍 Dietary Consultation - $50-75 (45-60 minutes)
- Comprehensive nutritional assessment
- Current diet evaluation
- Breed and life stage recommendations
- Feeding schedule optimization
- Nutritional deficiency identification

📋 Custom Nutrition Plan - $85-125 (60-75 minutes)
- Personalized meal planning with portions
- Ingredient recommendations and alternatives
- Feeding schedule with timing
- Supplement recommendations if needed
- Progress tracking guidelines

⚖️ Weight Management Program - $95-150 (90 minutes)
- Weight loss or gain strategies
- Calorie calculation and portion control
- Exercise and diet coordination
- Progress monitoring plan
- Metabolic assessment

🚫 Food Allergy Management - $75-100 (60-90 minutes)
- Elimination diet planning
- Hypoallergenic food recommendations
- Ingredient analysis and substitutions
- Allergy testing coordination
- Long-term management strategies

👴 Senior Pet Nutrition - $65-90 (45-60 minutes)
- Age-appropriate diet modifications
- Joint health nutrition support
- Digestive health optimization
- Cognitive function nutrition
- Quality of life enhancement

🏃 Performance Nutrition - $70-95 (60 minutes)
- Active and working dog nutrition
- Energy optimization for activities
- Recovery nutrition planning
- Hydration strategies
- Competition preparation diets

All consultations include detailed nutrition guides and follow-up support."""

@tool
def nutrition_assessment(dietary_concerns: str, pet_name: str = None, current_diet: str = ""):
    """Assess nutritional needs and provide dietary recommendations"""
    
    # Categorize dietary concerns
    weight_keywords = ['overweight', 'underweight', 'weight loss', 'weight gain', 'obesity']
    allergy_keywords = ['allergic', 'allergy', 'sensitive', 'intolerant', 'reaction']
    digestive_keywords = ['diarrhea', 'vomiting', 'upset stomach', 'digestive', 'gas']
    senior_keywords = ['senior', 'old', 'elderly', 'aging', 'arthritis']
    
    concerns_lower = dietary_concerns.lower()
    
    if any(keyword in concerns_lower for keyword in weight_keywords):
        concern_type = "WEIGHT MANAGEMENT"
        priority = "HIGH"
        recommendation = "⚖️ Weight Management Program recommended with calorie-controlled diet plan."
    elif any(keyword in concerns_lower for keyword in allergy_keywords):
        concern_type = "FOOD ALLERGIES"
        priority = "HIGH"
        recommendation = "🚫 Food Allergy Management with elimination diet approach."
    elif any(keyword in concerns_lower for keyword in digestive_keywords):
        concern_type = "DIGESTIVE HEALTH"
        priority = "MODERATE"
        recommendation = "🔍 Dietary Consultation focusing on digestive-friendly nutrition."
    elif any(keyword in concerns_lower for keyword in senior_keywords):
        concern_type = "SENIOR NUTRITION"
        priority = "MODERATE"
        recommendation = "👴 Senior Pet Nutrition consultation for age-appropriate diet."
    else:
        concern_type = "GENERAL NUTRITION"
        priority = "LOW"
        recommendation = "📋 Custom Nutrition Plan to optimize overall health."
    
    assessment = f"""🥗 Nutrition Assessment

📋 Dietary Concerns: {dietary_concerns}
🏷️ Concern Category: {concern_type}
⚠️ Priority Level: {priority}
🍽️ Current Diet: {current_diet if current_diet else 'Not specified'}

{recommendation}

💡 Nutritional Approach:
- Balanced macronutrient ratios
- High-quality protein sources
- Appropriate calorie density
- Essential fatty acids inclusion
- Vitamin and mineral optimization

📅 Recommended Plan:
- Initial consultation: 1 session
- Diet transition: 1-2 weeks
- Progress monitoring: 2-4 weeks
- Follow-up adjustments: As needed

⚠️ This is a preliminary assessment. Comprehensive nutrition consultation recommended for detailed meal planning."""

    return assessment

@tool
def modify_nutrition_appointment(customer_id: str, pet_name: str, old_date: str, new_date: str, new_time: str = None, new_service: str = None):
    """Modify an existing nutrition consultation appointment"""
    try:
        logger.info(f"🔄 Modifying nutrition appointment for {customer_id}, pet: {pet_name}")
        
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
def schedule_nutrition_appointment(customer_id: str, pet_name: str, service_type: str, preferred_date: str, preferred_time: str = "2:00 PM", notes: str = ""):
    """Schedule a nutrition consultation appointment with proper date/time validation"""
    try:
        # VALIDATE APPOINTMENT DATE AND TIME FIRST (using Bella's validation rules)
        validation_result = validate_appointment_availability(preferred_date, preferred_time)
        
        if not validation_result['available']:
            return f"""❌ Appointment Scheduling Failed

{validation_result['message']}

💡 Please choose a different date and time that meets our business requirements:
- Weekdays only (Monday-Friday)
- Business hours: 9:00 AM to 5:00 PM
- Future dates only (no past dates)
- No federal holidays

Would you like me to suggest some available appointment slots?"""
        
        appointment_id = f"NUTR_{uuid.uuid4().hex[:8].upper()}"
        
        appointment_data = {
            'appointment_id': appointment_id,
            'customer_id': customer_id,
            'pet_name': pet_name,
            'service_type': service_type,
            'date': validation_result['validated_date'],  # Use validated date
            'time': validation_result['validated_time'],  # Use validated time
            'notes': notes,
            'provider': 'Luna - Nutrition Specialist'
        }
        
        # Determine cost and duration based on service type
        service_costs = {
            'Dietary Consultation': {'cost': 65, 'duration': 50},
            'Custom Nutrition Plan': {'cost': 105, 'duration': 70},
            'Weight Management Program': {'cost': 125, 'duration': 90},
            'Food Allergy Management': {'cost': 85, 'duration': 75},
            'Senior Pet Nutrition': {'cost': 75, 'duration': 50},
            'Performance Nutrition': {'cost': 80, 'duration': 60}
        }
        
        service_info = service_costs.get(service_type, {'cost': 75, 'duration': 60})
        appointment_data['cost'] = service_info['cost']
        appointment_data['duration'] = service_info['duration']
        
        # Save appointment
        if save_appointment_with_logging(appointment_data):
            # Format the date nicely for display
            from datetime import datetime as dt
            display_date = dt.strptime(validation_result['validated_date'], '%Y-%m-%d').strftime('%B %d, %Y')
            display_time = dt.strptime(validation_result['validated_time'], '%H:%M').strftime('%I:%M %p')
            
            return f"""✅ Nutrition Consultation Scheduled Successfully!

📋 Appointment Details:
- Appointment ID: {appointment_id}
- Pet: {pet_name}
- Service: {service_type}
- Date: {display_date}
- Time: {display_time}
- Duration: {service_info['duration']} minutes
- Cost: ${service_info['cost']}
- Nutritionist: Luna (Nutrition Specialist)

📝 Notes: {notes if notes else 'None'}

💡 Preparation Instructions:
- Bring current food packaging/labels
- List all treats and supplements given
- Note feeding schedule and portions
- Prepare questions about dietary goals
- Bring recent weight measurements if available

🥗 Nutrition Philosophy: We focus on balanced, species-appropriate nutrition tailored to your pet's individual needs."""
        else:
            return f"❌ Error scheduling appointment. Please try again or contact us directly."
        
    except Exception as e:
        logger.error(f"Error scheduling nutrition appointment: {e}")
        return f"❌ Error scheduling appointment: {str(e)}. Please try again or contact us directly."

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
def save_conversation_memory(customer_id: str, user_message: str, luna_response: str, session_id: str = None):
    """Save current conversation to AgentCore Memory"""
    try:
        # Initialize memory if not already done
        if not memory_id:
            initialize_memory(customer_id, session_id)
        
        save_conversation_to_memory(customer_id, session_id or "default", user_message, luna_response)
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

# Create base tools list (nutrition-specific tools)
base_tools = [
    get_customer_and_pet_info,
    nutrition_services,
    nutrition_assessment,
    schedule_nutrition_appointment,
    modify_nutrition_appointment,
    list_customer_appointments,
    get_memory_context,
    save_conversation_memory
]

# Create Strands agent with all tools (enhanced with memory tools when available)
agent = Agent(
    model=model,
    tools=base_tools,
    system_prompt="""You are Luna, a knowledgeable and encouraging pet nutrition specialist at GenAI Pet Store.

CRITICAL: You MUST use your tools to provide accurate information. Never guess or make up information.

🔧 **MANDATORY Tool Usage Rules:**
1. When a customer provides a customer ID or asks about their pets/dietary needs, ALWAYS use get_customer_and_pet_info tool FIRST
2. When asked about nutrition services, pricing, or dietary programs, ALWAYS use nutrition_services tool
3. When asked to assess dietary concerns, ALWAYS use nutrition_assessment tool
4. When asked to schedule nutrition consultations, ALWAYS use schedule_nutrition_appointment tool
5. NEVER provide customer or pet dietary information without using the tools first

🥗 **Your Available Tools:**
- get_customer_and_pet_info(customer_id, pet_name=None): Look up customer and pet data including dietary information
- nutrition_services(): Get current nutrition services, pricing, and dietary programs
- nutrition_assessment(dietary_concerns, pet_name=None, current_diet=""): Assess nutritional needs and provide recommendations
- schedule_nutrition_appointment(customer_id, pet_name, service_type, preferred_date, notes=""): Book NEW nutrition consultations
- modify_nutrition_appointment(customer_id, pet_name, old_date, new_date, new_time=None, new_service=None): MODIFY existing nutrition appointments
- list_customer_appointments(customer_id): Get fresh appointment data from database
- get_memory_context(customer_id, session_id=None): Retrieve conversation history
- save_conversation_memory(customer_id, user_message, luna_response, session_id=None): Save conversation context

🎯 **Critical Response Patterns:**
1. Customer asks about pets/dietary info → IMMEDIATELY use get_customer_and_pet_info tool
2. Customer asks about nutrition services/pricing → IMMEDIATELY use nutrition_services tool
3. Customer mentions dietary concerns → IMMEDIATELY use nutrition_assessment tool
4. Customer wants to book nutrition consultation → Use schedule_nutrition_appointment tool

🚨 **NUTRITION FOCUS AREAS:**
- Weight management (loss/gain strategies)
- Food allergies and sensitivities
- Life stage nutrition (puppy, adult, senior)
- Breed-specific dietary needs
- Therapeutic diets for health conditions
- Performance nutrition for active pets

🚨 **ENHANCED APPROACH:**
- Always use the customer's actual name and pet names from the database
- Ask about pet's current diet, age, weight, and activity level from the database
- Provide personalized nutrition recommendations based on breed and life stage
- Reference pet's current diet and dietary restrictions from the database
- Create actionable meal plans with specific portions when requested
- Be supportive, educational, and data-driven in your recommendations

🚨 **NUTRITION CONSULTATION REQUIREMENTS:**
- For NEW consultations: Use schedule_nutrition_appointment tool
- For CHANGING/MODIFYING consultations: Use modify_nutrition_appointment tool
- For LISTING appointments: Use list_customer_appointments tool to get fresh data from database
- For dietary assessments: Use nutrition_assessment tool with specific concerns
- For service information: Use nutrition_services tool to show available programs
- Always reference actual customer and pet data from the database
- Provide evidence-based nutrition advice tailored to each pet's needs
- After modifying appointments, confirm the change was saved to the database

🕒 **BUSINESS HOURS & AVAILABILITY:**
- Business Hours: 9:00 AM to 5:00 PM, Monday through Friday ONLY
- CLOSED: Saturdays, Sundays, and US federal holidays
- If customer requests weekend/holiday/outside hours: Politely decline and suggest alternative times
- When customer doesn't specify time, suggest: "What time would you prefer? Our hours are 9:00 AM to 5:00 PM, Monday-Friday."

Be supportive, educational, and encouraging in your nutrition guidance. Always use the appropriate tools and reference actual customer data to provide personalized dietary recommendations."""
)

@app.entrypoint
def luna_nutrition_agent(payload, context):
    """
    Luna Nutrition Agent with complete memory, session, and DynamoDB integration
    """
    try:
        user_input = payload.get("prompt", "Hello! How can I help you with your pet's nutrition today?")
        customer_id = payload.get("customer_id", "")
        session_id = context.session_id or ""
        
        logger.info(f"🥗 Luna Agent - Processing request for customer: {customer_id}")
        logger.info(f"🔗 Session ID: {session_id}")
        
        # Extract context from user input to improve understanding
        conversation_context = extract_conversation_context(user_input)
        if conversation_context:
            logger.info(f"🧠 Extracted context: {conversation_context}")
        
        # Initialize memory for this customer/session (preserving existing logic)
        current_agent = agent  # Use the global agent by default
        
        if customer_id or session_id:
            initialize_memory(customer_id, session_id)
            # Also initialize enhanced memory tools if available
            if MEMORY_TOOLS_AVAILABLE and customer_id:
                memory_provider = initialize_memory_tools(customer_id, session_id)
                # Enhance agent with memory tools for this session (non-destructive)
                if memory_provider and hasattr(memory_provider, 'tools'):
                    try:
                        # Create enhanced agent with memory tools for this conversation
                        enhanced_tools = base_tools + memory_provider.tools
                        current_agent = Agent(model=model, tools=enhanced_tools)
                        logger.info(f"✅ Enhanced agent with {len(memory_provider.tools)} memory tools")
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
        logger.error(f"❌ Error in Luna agent: {e}")
        return f"I apologize, but I encountered an error: {str(e)}. Please try again or contact support."

if __name__ == "__main__":
    app.run()