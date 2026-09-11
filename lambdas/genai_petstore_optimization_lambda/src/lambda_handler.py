#!/usr/bin/env python3
"""
Lambda Handler for Agent Optimization System
Handles HTTP API Gateway requests for performance testing and optimization scenarios
"""

import json
import logging
import traceback
import time
from datetime import datetime

# Import optimization modules
from scenario_router import ScenarioRouter

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Main Lambda handler for optimization API
    
    Supported routes:
    - POST /optimize - Execute single optimization scenario
    - POST /parallel - Execute parallel fault+baseline scenarios
    - GET /scenarios - List available scenarios
    - GET /results/{execution_id} - Get execution results
    - GET /health - Health check
    """
    
    logger.info(f"Received event: {json.dumps(event)}")
    
    # ===== X-RAY TRACE PROPAGATION =====
    # Extract X-Ray trace header from API Gateway
    headers = event.get('headers', {})
    trace_header = headers.get('X-Amzn-Trace-Id') or headers.get('x-amzn-trace-id')
    
    # Parse trace components
    trace_id = ''
    trace_parent = ''
    if trace_header:
        parts = trace_header.split(';')
        for part in parts:
            if part.startswith('Root='):
                trace_id = part.split('=')[1]
            elif part.startswith('Parent='):
                trace_parent = part.split('=')[1]
        
        logger.info(f"📍 ===== LAMBDA X-RAY TRACE CONTEXT =====")
        logger.info(f"📍 Full Trace Header: {trace_header}")
        logger.info(f"📍 Trace ID (Root): {trace_id}")
        logger.info(f"📍 Trace Parent: {trace_parent}")
        logger.info(f"📍 Will propagate to downstream services")
        logger.info(f"📍 ====================================")
    
    # Store trace context for downstream propagation
    trace_context = {
        'trace_header': trace_header,
        'trace_id': trace_id,
        'trace_parent': trace_parent
    }
    
    # Store in event for access by handlers
    event['trace_context'] = trace_context
    
    try:
        # Parse request
        http_method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        path = event.get('requestContext', {}).get('http', {}).get('path', '/')
        body = event.get('body', '{}')
        
        # Parse body if present
        if body:
            try:
                body_data = json.loads(body) if isinstance(body, str) else body
            except json.JSONDecodeError:
                return error_response(400, "Invalid JSON in request body")
        else:
            body_data = {}
        
        # Route to appropriate handler
        if path == '/health' or path == '/prod/health':
            return handle_health()
        
        elif path == '/scenarios' or path == '/prod/scenarios':
            return handle_list_scenarios()
        
        elif path == '/optimize' or path == '/prod/optimize' or path == '/execute-scenario' or path == '/prod/execute-scenario':
            if http_method == 'POST':
                return handle_optimize(body_data, trace_context)
            else:
                return error_response(405, "Method not allowed")
        
        elif path == '/parallel' or path == '/prod/parallel':
            if http_method == 'POST':
                return handle_parallel(body_data, trace_context)
            else:
                return error_response(405, "Method not allowed")
        
        elif '/results/' in path:
            execution_id = path.split('/results/')[-1]
            return handle_get_results(execution_id)
        
        else:
            return error_response(404, f"Route not found: {path}")
    
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        logger.error(traceback.format_exc())
        return error_response(500, f"Internal server error: {str(e)}")


def handle_health():
    """Health check endpoint"""
    return success_response({
        'status': 'healthy',
        'service': 'agent-optimization',
        'timestamp': datetime.utcnow().isoformat()
    })


def handle_list_scenarios():
    """List all available scenarios"""
    try:
        router = ScenarioRouter()
        scenarios = router.scenarios  # This is a dict with int keys
        
        # Format scenarios for response
        scenario_list = []
        for scenario_id, scenario_config in scenarios.items():
            scenario_list.append({
                'id': scenario_config.scenario_id,
                'name': scenario_config.scenario_name,
                'type': scenario_config.scenario_type,
                'description': scenario_config.description,
                'expected_impact': scenario_config.expected_impact
            })
        
        return success_response({
            'scenarios': scenario_list,
            'total': len(scenario_list)
        })
    
    except Exception as e:
        logger.error(f"Error listing scenarios: {e}")
        return error_response(500, f"Failed to list scenarios: {str(e)}")


def handle_optimize(body_data, trace_context=None):
    """Execute single optimization scenario"""
    try:
        # Validate required fields
        required_fields = ['prompt', 'scenario_id']
        for field in required_fields:
            if field not in body_data:
                return error_response(400, f"Missing required field: {field}")
        
        prompt = body_data['prompt']
        scenario_id = body_data['scenario_id']
        customer_id = body_data.get('customer_id', 'cust_matthewnguyen22')
        session_id = body_data.get('session_id', f'session_{datetime.utcnow().timestamp()}')
        
        # Parse scenario
        router = ScenarioRouter()
        scenario_config = router.get_scenario_by_id(scenario_id)
        
        if not scenario_config:
            return error_response(404, f"Scenario not found: {scenario_id}")
        
        # Execute scenario with REAL agent invocation
        from optimization_executors import execute_scenario_with_agent
        
        # Create simple context object
        class SimpleContext:
            def __init__(self, user_input, customer_id, session_id):
                self.user_input = user_input
                self.customer_id = customer_id
                self.session_id = session_id
        
        context = SimpleContext(prompt, customer_id, session_id)
        
        # Execute the scenario and collect REAL metrics
        result = execute_scenario_with_agent(scenario_config, context)
        
        # Flatten metrics to top level for frontend compatibility
        # Frontend expects: {fault: {latency_ms, cost_usd, total_tokens, response, ...}}
        flattened_result = {
            'execution_id': result.get('execution_id'),
            'scenario_id': result.get('scenario_id'),
            'scenario_name': result.get('scenario_name'),
            'scenario_type': result.get('scenario_type'),
            'status': result.get('status'),
            'response': result.get('response'),
            'timestamp': result.get('timestamp'),
            # Flatten metrics to top level
            'latency_ms': result.get('metrics', {}).get('latency_ms', 0),
            'estimated_cost_usd': result.get('metrics', {}).get('estimated_cost_usd', 0),
            'total_tokens': result.get('metrics', {}).get('total_tokens', 0),
            'input_tokens': result.get('metrics', {}).get('input_tokens', 0),
            'output_tokens': result.get('metrics', {}).get('output_tokens', 0),
            'tool_calls': result.get('metrics', {}).get('tool_calls', 0)
        }
        
        # Wrap in 'fault' key for frontend compatibility
        wrapped_result = {
            'fault': flattened_result,
            'baseline': None,
            'comparison': None
        }
        
        return success_response(wrapped_result)
    
    except Exception as e:
        logger.error(f"Error executing optimization: {e}")
        logger.error(traceback.format_exc())
        return error_response(500, f"Execution failed: {str(e)}")


def handle_parallel(body_data, trace_context=None):
    """Execute parallel fault+baseline scenarios"""
    try:
        # Log trace propagation
        if trace_context and trace_context.get('trace_id'):
            logger.info(f"📍 handle_parallel received trace_id: {trace_context['trace_id']}")
        
        # Validate required fields
        required_fields = ['prompt', 'scenario_id']
        for field in required_fields:
            if field not in body_data:
                return error_response(400, f"Missing required field: {field}")
        
        prompt = body_data['prompt']
        scenario_id = body_data['scenario_id']
        customer_id = body_data.get('customer_id', 'cust_matthewnguyen22')
        session_id = body_data.get('session_id', f'session_{datetime.utcnow().timestamp()}')
        async_mode = body_data.get('async', False)
        
        # Parse scenario
        router = ScenarioRouter()
        scenario_config = router.get_scenario_by_id(scenario_id)
        
        if not scenario_config:
            return error_response(404, f"Scenario not found: {scenario_id}")
        
        # Check if this is a baseline scenario - if so, return helpful message
        if scenario_config.scenario_type == 'baseline':
            # For baseline scenarios, execute it once and return as both results
            from optimization_executors import execute_scenario_with_agent
            
            class SimpleContext:
                def __init__(self, user_input, customer_id, session_id):
                    self.user_input = user_input
                    self.customer_id = customer_id
                    self.session_id = session_id
            
            context = SimpleContext(prompt, customer_id, session_id)
            result = execute_scenario_with_agent(scenario_config, context)
            
            # Return same result for both sides with explanation
            return success_response({
                'execution_id': f"baseline_{int(time.time() * 1000)}",
                'fault_result': result,
                'baseline_result': result,
                'comparison': {
                    'latency_delta_ms': 0,
                    'latency_delta_percent': 0,
                    'token_delta': 0,
                    'token_delta_percent': 0,
                    'cost_delta_usd': 0,
                    'tool_call_delta': 0
                },
                'root_cause_analysis': f"Scenario {scenario_id} is a baseline scenario (optimal performance). To see a comparison with fault injection, please select a fault_injection scenario like Scenario 2 (Context Bloat) or Scenario 10 (DynamoDB Latency Spike).",
                'timestamp': datetime.utcnow().isoformat(),
                'note': 'This is a baseline scenario - both sides show the same optimal execution. Select a fault_injection scenario to see performance differences.'
            })
        
        # Handle optimization scenarios differently - they don't have baselines
        if scenario_config.scenario_type == 'optimization':
            return error_response(400, f"Scenario {scenario_id} is an optimization scenario. Parallel execution is only supported for fault_injection scenarios. Optimization scenarios compare different strategies internally and don't need baseline comparison.")
        
        # Get baseline scenario for fault scenarios
        baseline_config = router.get_baseline_scenario(scenario_id)
        
        if not baseline_config:
            return error_response(400, f"No baseline scenario defined for scenario {scenario_id}")
        
        # Execute parallel scenarios with REAL agent invocations
        from optimization_executors import execute_parallel_scenarios
        
        # Create simple context object
        class SimpleContext:
            def __init__(self, user_input, customer_id, session_id):
                self.user_input = user_input
                self.customer_id = customer_id
                self.session_id = session_id
        
        context = SimpleContext(prompt, customer_id, session_id)
        
        # Execute both scenarios in parallel and collect REAL metrics
        # Pass trace_context for X-Ray propagation
        logger.info(f"📍 Passing trace_context to execute_parallel_scenarios")
        result = execute_parallel_scenarios(scenario_config, baseline_config, context, trace_context)
        
        # Always return results immediately (sync mode)
        # Async mode with DynamoDB storage can be added later if needed
        return success_response(result)
    
    except Exception as e:
        logger.error(f"Error executing parallel scenarios: {e}")
        logger.error(traceback.format_exc())
        return error_response(500, f"Parallel execution failed: {str(e)}")


def handle_get_results(execution_id):
    """Get execution results by ID"""
    try:
        # TODO: Implement result retrieval from DynamoDB
        # For now, return mock response
        
        return success_response({
            'execution_id': execution_id,
            'status': 'not_found',
            'message': 'Result retrieval not yet implemented'
        })
    
    except Exception as e:
        logger.error(f"Error retrieving results: {e}")
        return error_response(500, f"Failed to retrieve results: {str(e)}")


def success_response(data, status_code=200):
    """Format success response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': '*'
        },
        'body': json.dumps(data)
    }


def error_response(status_code, message):
    """Format error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': '*'
        },
        'body': json.dumps({
            'error': message,
            'timestamp': datetime.utcnow().isoformat()
        })
    }
