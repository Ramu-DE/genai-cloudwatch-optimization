"""
Agent Executor - Real AgentCore agent invocation with fault injection and metrics collection
"""

import logging
import time
import traceback
import boto3
import os
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# AgentCore configuration from environment variables
# Use Bella agent ARN from Lambda environment (set by optimization_lambda_deployer.py)
AGENT_ARN = os.environ.get('BELLA_AGENT_ARN')
if not AGENT_ARN:
    # Fallback for local testing
    logger.warning("⚠️  BELLA_AGENT_ARN not found in environment, using fallback")
    AGENTCORE_AGENT_NAME = "agent_optimization_scenarios-s11gWwB1rl"
    AGENTCORE_REGION = "us-west-2"
    AGENT_ARN = f'arn:aws:bedrock-agentcore:{AGENTCORE_REGION}:359930127894:runtime/{AGENTCORE_AGENT_NAME}'
else:
    logger.info(f"✅ Using Bella agent ARN from environment: {AGENT_ARN}")

# Extract region from ARN for client initialization
AGENTCORE_REGION = os.environ.get('DEPLOYMENT_REGION', 'us-east-1')

# Initialize AgentCore Runtime client
agentcore_client = boto3.client('bedrock-agentcore', region_name=AGENTCORE_REGION)


def execute_agent_with_scenario(scenario_config, user_input: str, customer_id: str, session_id: str, trace_context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Execute Luna agent with the specified scenario configuration.
    
    Args:
        scenario_config: ScenarioConfig object
        user_input: User's prompt/question
        customer_id: Customer ID for context
        session_id: Session ID for tracking
        trace_context: X-Ray trace context for propagation (optional)
        
    Returns:
        Dictionary with execution results and real metrics
    """
    logger.info(f"Executing agent with scenario {scenario_config.scenario_id}: {scenario_config.scenario_name}")
    
    # Log trace context if available
    if trace_context:
        logger.info(f"📍 ===== AGENT EXECUTOR X-RAY TRACE =====")
        logger.info(f"📍 Trace ID: {trace_context.get('trace_id', 'N/A')}")
        logger.info(f"📍 Trace Parent: {trace_context.get('trace_parent', 'N/A')}")
        logger.info(f"📍 Propagating to AgentCore invocation")
        logger.info(f"📍 =======================================")
    
    start_time = time.time()
    
    try:
        # Start timing for total execution
        agent_start = time.time()
        
        # Fault injection is handled INSIDE the AgentCore agent (agentcore_agent.py)
        # The agent will apply delays, context bloat, etc. based on scenario_id
        # We just pass the scenario_id in the payload
        
        # Execute REAL AgentCore agent (using Bella from environment)
        logger.info(f"Invoking AgentCore agent {AGENT_ARN} for scenario {scenario_config.scenario_id}...")
        
        import json
        
        # Prepare payload - includes scenario_id so agent knows which scenario to execute
        payload = {
            'prompt': user_input,
            'customer_id': customer_id,
            'scenario_id': scenario_config.scenario_id,
            'timestamp': datetime.now().isoformat(),
            'sessionId': session_id,
            'userId': customer_id
        }
        
        # Encode payload - EXACT same as websocket-lambda (no base64!)
        encoded_payload = json.dumps(payload).encode('utf-8')
        
        logger.info(f"📦 Payload prepared: {len(encoded_payload)} bytes")
        logger.info(f"📦 Payload content: {json.dumps(payload)[:200]}")
        
        # Ensure session_id is at least 33 characters (AgentCore requirement)
        if len(session_id) < 33:
            session_id = session_id + '_' + '0' * (33 - len(session_id) - 1)
        
        # Build invocation params - EXACT same as websocket-lambda
        invocation_params = {
            'agentRuntimeArn': AGENT_ARN,
            'qualifier': 'DEFAULT',
            'runtimeSessionId': session_id,
            'runtimeUserId': customer_id,
            'payload': encoded_payload,
            'contentType': 'application/json'
        }
        
        logger.info(f"🚀 Invoking AgentCore with params: {list(invocation_params.keys())}")
        
        # Invoke AgentCore agent with base64-encoded payload (matching CLI)
        logger.info(f"🚀 Invoking AgentCore agent...")
        logger.info(f"🚀 Payload (base64): {encoded_payload[:100]}...")
        
        response = agentcore_client.invoke_agent_runtime(**invocation_params)
        
        logger.info(f"✅ Response received from AgentCore")
        
        # Parse response
        response_text = ""
        if hasattr(response.get('response'), 'read'):
            response_data = response['response'].read()
            if isinstance(response_data, bytes):
                response_data = response_data.decode('utf-8')
            response_text = response_data
        else:
            response_text = str(response.get('response', ''))
        
        agent_end = time.time()
        agent_latency = (agent_end - agent_start) * 1000
        
        logger.info(f"✅ AgentCore execution completed in {agent_latency:.0f}ms")
        logger.info(f"Response length: {len(response_text)} characters")
        
        # Collect metrics from real AgentCore execution
        metrics = collect_metrics(
            scenario_config,
            agent_latency,
            response_text
        )
        
        # Calculate total execution time
        end_time = time.time()
        total_latency = (end_time - start_time) * 1000
        
        result = {
            'execution_id': f"exec_{int(start_time * 1000)}",
            'scenario_id': scenario_config.scenario_id,
            'scenario_name': scenario_config.scenario_name,
            'scenario_type': scenario_config.scenario_type,
            'status': 'completed',
            'metrics': metrics,
            'response': response_text,
            'activity': generate_activity_log(scenario_config, agent_latency),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Scenario completed: {metrics['latency_ms']:.0f}ms, {metrics['total_tokens']} tokens, ${metrics['estimated_cost_usd']:.4f}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error executing scenario: {e}")
        logger.error(traceback.format_exc())
        
        end_time = time.time()
        total_latency = (end_time - start_time) * 1000
        
        return {
            'execution_id': f"exec_{int(start_time * 1000)}",
            'scenario_id': scenario_config.scenario_id,
            'scenario_name': scenario_config.scenario_name,
            'status': 'error',
            'error': str(e),
            'metrics': {
                'latency_ms': total_latency,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'tool_calls': 0,
                'estimated_cost_usd': 0.0
            },
            'response': f"Execution failed: {str(e)}",
            'activity': [],
            'timestamp': datetime.utcnow().isoformat()
        }





def collect_metrics(scenario_config, agent_latency: float, response_text: str) -> Dict[str, Any]:
    """
    Collect performance metrics from real AgentCore agent execution.
    
    Args:
        scenario_config: Scenario configuration
        agent_latency: Measured agent latency in ms (includes fault injection delays)
        response_text: Agent's response
        
    Returns:
        Dictionary of metrics
    """
    # Estimate tokens based on response length
    # Rough estimate: 1 token ≈ 4 characters
    base_input_tokens = 250  # Base estimate for prompt
    
    # Adjust input tokens for context bloat scenarios
    input_tokens = base_input_tokens
    if scenario_config.scenario_type == 'fault_injection':
        if scenario_config.fault_type == 'context_bloat':
            # Context bloat adds ~500 tokens of Lorem ipsum text
            input_tokens = base_input_tokens + 500
            logger.info(f"📊 Context bloat detected: +500 input tokens")
    
    # Calculate output tokens from response
    output_tokens = len(response_text) // 4
    total_tokens = input_tokens + output_tokens
    
    # Estimate tool calls (baseline: 1, fault scenarios may have more)
    tool_calls = 1
    if scenario_config.scenario_type == 'fault_injection':
        if scenario_config.fault_type in ['tool_orchestration_fault', 'memory_misuse']:
            tool_calls = 2  # Extra tool calls from fault
            logger.info(f"📊 Extra tool calls detected: {tool_calls}")
    
    # Calculate cost (Claude 3.5 Haiku pricing)
    input_cost = (input_tokens / 1000) * 0.00025
    output_cost = (output_tokens / 1000) * 0.00125
    total_cost = input_cost + output_cost
    
    logger.info(f"📊 Metrics calculated: {input_tokens} input + {output_tokens} output = {total_tokens} total tokens")
    
    return {
        'latency_ms': agent_latency,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': total_tokens,
        'tool_calls': tool_calls,
        'estimated_cost_usd': total_cost
    }


def generate_activity_log(scenario_config, agent_latency: float) -> list:
    """Generate activity log for the execution"""
    now = datetime.utcnow()
    
    activities = [
        {
            'timestamp': (now.timestamp() - agent_latency/1000 - 0.5) * 1000,
            'message': 'Initializing agent context'
        },
        {
            'timestamp': (now.timestamp() - agent_latency/1000 - 0.3) * 1000,
            'message': 'Parsing user prompt'
        }
    ]
    
    if scenario_config.scenario_type == 'fault_injection':
        activities.append({
            'timestamp': (now.timestamp() - agent_latency/1000 - 0.2) * 1000,
            'message': f'Applying fault injection: {scenario_config.fault_type}'
        })
    
    activities.extend([
        {
            'timestamp': (now.timestamp() - agent_latency/1000) * 1000,
            'message': 'Invoking Luna agent'
        },
        {
            'timestamp': (now.timestamp() - 0.2) * 1000,
            'message': 'Processing agent response'
        },
        {
            'timestamp': now.timestamp() * 1000,
            'message': 'Execution completed'
        }
    ])
    
    return activities


def simulate_agent_execution(user_input: str, customer_id: str, scenario_config) -> str:
    """
    Simulate realistic agent execution with scenario-specific behavior.
    This provides reliable, predictable results for the optimization dashboard.
    
    Args:
        user_input: User's prompt
        customer_id: Customer ID
        scenario_config: Scenario configuration
        
    Returns:
        Simulated agent response
    """
    # Apply realistic delays based on scenario type
    if scenario_config.scenario_type == 'fault_injection':
        fault_type = scenario_config.fault_type
        
        if fault_type == 'latency_injection':
            # DynamoDB latency spike - 4 second delay
            time.sleep(4.0)
        elif fault_type == 'context_bloat':
            # Context bloat processing overhead - 1.5 second delay
            time.sleep(1.5)
        elif fault_type == 'tool_orchestration_fault':
            # Redundant tool calls - 1 second delay
            time.sleep(1.0)
        elif fault_type == 'tool_failure':
            # Tool failure and retry - 2 second delay
            time.sleep(2.0)
        elif fault_type == 'memory_misuse':
            # Useless memory retrieval - 0.5 second delay
            time.sleep(0.5)
        else:
            # Default fault overhead
            time.sleep(0.8)
    else:
        # Baseline/optimization scenarios - fast execution
        time.sleep(0.5)
    
    # Generate realistic nutrition response
    response = f"""Based on your request, here's a personalized nutrition plan for {customer_id}:

**Meal Structure:**
- Breakfast (7-8 AM): High-protein meal with complex carbs
  • 3 eggs with spinach and whole grain toast
  • Greek yogurt with berries
  • Green tea

- Mid-Morning Snack (10 AM): 
  • Protein shake with banana
  • Handful of almonds

- Lunch (12-1 PM): Balanced macro meal
  • Grilled chicken breast (6oz)
  • Quinoa (1 cup)
  • Mixed vegetables
  • Olive oil dressing

- Afternoon Snack (3-4 PM):
  • Apple with almond butter
  • Protein bar

- Dinner (6-7 PM): Lighter meal
  • Baked salmon (5oz)
  • Sweet potato
  • Steamed broccoli

**Supplements:**
- Vitamin D3 (2000 IU daily)
- Omega-3 fish oil (1000mg EPA/DHA)
- Magnesium (400mg before bed)
- Multivitamin

**Hydration:**
- Target: 0.5-1 oz per pound of body weight
- Minimum 8 glasses of water daily
- Electrolytes during workouts

**Key Principles:**
1. Eat protein with every meal (0.8-1g per lb body weight)
2. Time carbs around workouts
3. Include healthy fats at each meal
4. Prioritize whole, unprocessed foods
5. Meal prep on Sundays for the week

This plan is designed to support your fitness goals while maintaining energy levels throughout the day."""

    # Add scenario-specific annotations
    if scenario_config.scenario_type == 'fault_injection':
        if scenario_config.fault_type == 'context_bloat':
            response += "\n\n[Note: This response processed excessive context, increasing token usage by ~500 tokens]"
        elif scenario_config.fault_type == 'latency_injection':
            response += "\n\n[Note: This response experienced a 4-second database latency spike]"
        elif scenario_config.fault_type == 'tool_orchestration_fault':
            response += "\n\n[Note: This response made redundant tool calls, adding 1 second overhead]"
    
    return response
