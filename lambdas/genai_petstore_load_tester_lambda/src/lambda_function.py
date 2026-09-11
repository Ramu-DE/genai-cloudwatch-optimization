"""
Load Tester Lambda Function
Simple load testing Lambda for AgentCore agents
"""

import json
import boto3
import time
import uuid
import os
from datetime import datetime
from decimal import Decimal

# Initialize AWS clients
bedrock_agentcore = boto3.client('bedrock-agentcore')
dynamodb = boto3.resource('dynamodb')
lambda_client = boto3.client('lambda')

# DynamoDB table for storing load test results
LOAD_TEST_RESULTS_TABLE = os.environ.get('LOAD_TEST_RESULTS_TABLE', 'genai_petstore_load_test_results')

def get_load_test_session_id(customer_id, request_index):
    """
    Generate 33-char session ID for load testing.
    Matches frontend JavaScript logic:
    - Extract customer name from customer_id (remove 'cust_' prefix)
    - Add random string
    - Format: cust_{customerName}_{random}
    - Truncate to 33 characters if needed
    """
    import hashlib
    
    # Extract customer name (remove 'cust_' prefix if present)
    customer_name = customer_id.replace('cust_', '') if customer_id.startswith('cust_') else customer_id
    
    # Generate random string (similar to JavaScript Math.random().toString(36).substring(2, 15))
    timestamp_ms = int(time.time() * 1000)
    random_base = f"{timestamp_ms}_{request_index}"
    random_hex = hashlib.md5(random_base.encode()).hexdigest()[:13]  # 13 chars like JS substring(2, 15)
    
    # Create session ID: cust_{customerName}_{random}
    session_id = f"cust_{customer_name}_{random_hex}"
    
    # Truncate to 33 characters if needed (AgentCore compliant)
    if len(session_id) > 33:
        session_id = session_id[:33]
    
    return session_id

def process_async_load_test(event):
    """Process load test asynchronously in background"""
    test_id = event.get('test_id')
    agent_name = event.get('agent_name')
    agent_arn = event.get('agent_arn')
    num_requests = event.get('num_requests', 10)
    prompt = event.get('prompt', 'Hello')
    
    print(f"Processing async load test {test_id} with {num_requests} requests")
    
    results = {
        'successful': 0,
        'failed': 0,
        'durations': [],
        'errors': []
    }
    
    is_fargate = agent_arn.startswith('http')
    table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
    
    # Run all requests
    for i in range(num_requests):
        try:
            start_time = time.time()
            
            # Generate session ID
            customer_id = 'cust_matthewnguyen22'
            session_id = get_load_test_session_id(customer_id, i)
            
            if is_fargate:
                # For Fargate (Max agent), make HTTP request
                import urllib3
                http = urllib3.PoolManager()
                
                fargate_response = http.request(
                    'POST',
                    agent_arn,
                    body=json.dumps({
                        'prompt': prompt,
                        'customerId': 'cust_matthewnguyen22',
                        'sessionId': session_id
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            else:
                # For AgentCore Runtime agents
                payload = {
                    'prompt': prompt,
                    'customer_id': 'cust_matthewnguyen22',
                    'sessionId': session_id,
                    'userId': 'cust_matthewnguyen22'
                }
                encoded_payload = json.dumps(payload).encode('utf-8')
                
                response = bedrock_agentcore.invoke_agent_runtime(
                    agentRuntimeArn=agent_arn,
                    qualifier='DEFAULT',
                    runtimeSessionId=session_id,
                    runtimeUserId='cust_matthewnguyen22',
                    payload=encoded_payload,
                    contentType='application/json'
                )
                
                # Consume response
                if hasattr(response.get('response'), 'read'):
                    response['response'].read()
            
            duration = time.time() - start_time
            results['durations'].append(Decimal(str(duration * 1000)))
            results['successful'] += 1
            
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(str(e))
        
        # Update progress in DynamoDB every request
        try:
            table.update_item(
                Key={'test_id': test_id},
                UpdateExpression='SET completed = :c, successful = :s, failed = :f, durations = :d, errors = :e',
                ExpressionAttributeValues={
                    ':c': i + 1,
                    ':s': results['successful'],
                    ':f': results['failed'],
                    ':d': results['durations'],
                    ':e': results['errors']
                }
            )
        except Exception as e:
            print(f"Error updating progress: {e}")
    
    # Calculate final stats
    if results['durations']:
        stats = {
            'avg_duration': Decimal(str(float(sum(results['durations']) / len(results['durations'])))),
            'min_duration': Decimal(str(float(min(results['durations'])))),
            'max_duration': Decimal(str(float(max(results['durations']))))
        }
    else:
        stats = {}
    
    # Mark test as complete
    try:
        update_expr = 'SET #status = :status, completed_at = :completed_at'
        expr_values = {
            ':status': 'completed',
            ':completed_at': datetime.now().isoformat()
        }
        
        # Only add stats if we have them
        if stats:
            update_expr += ', stats = :stats'
            expr_values[':stats'] = stats
        
        table.update_item(
            Key={'test_id': test_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues=expr_values
        )
        print(f"Successfully marked test {test_id} as completed")
    except Exception as e:
        print(f"Error marking test complete: {e}")
        import traceback
        print(traceback.format_exc())
    
    print(f"Async load test {test_id} completed: {results['successful']} successful, {results['failed']} failed")

def decimal_to_float(obj):
    """Recursively convert Decimal objects to float/int for JSON serialization"""
    if isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: decimal_to_float(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        # Convert to int if it's a whole number, otherwise float
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    else:
        return obj

def get_load_test_results(test_id):
    """Get results of an async load test"""
    try:
        print(f"Getting results for test_id: {test_id}")
        print(f"Table name: {LOAD_TEST_RESULTS_TABLE}")
        
        table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
        response = table.get_item(Key={'test_id': test_id})
        
        print(f"DynamoDB response keys: {list(response.keys())}")
        
        if 'Item' not in response:
            print(f"Test not found: {test_id}")
            return respond(404, {'error': 'Test not found'})
        
        item = response['Item']
        print(f"Item keys: {list(item.keys())}")
        
        # Convert all Decimal objects to float/int for JSON serialization
        item = decimal_to_float(item)
        
        return respond(200, item)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error getting results: {error_details}")
        return respond(500, {'error': f'Failed to get results: {str(e)}', 'details': error_details})

def lambda_handler(event, context):
    """Main Lambda handler"""
    
    # Check if this is an async processing invocation
    if event.get('action') == 'process_load_test':
        process_async_load_test(event)
        return  # No response needed for async processing
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': ''
        }
    
    # Parse request
    try:
        if event.get('body'):
            body = json.loads(event['body'])
        else:
            body = event
    except:
        body = event
    
    # Route based on path
    path = event.get('path', event.get('rawPath', '/'))
    method = event.get('httpMethod', event.get('requestContext', {}).get('http', {}).get('method', 'GET'))
    
    print(f"Request: {method} {path}")
    print(f"Body keys: {list(body.keys()) if isinstance(body, dict) else 'not a dict'}")
    print(f"Event keys: {list(event.keys())}")
    
    # Health check
    if path == '/health' or path == '/':
        return respond(200, {
            'status': 'healthy',
            'service': 'Load Tester',
            'timestamp': datetime.now().isoformat()
        })
    
    # Single invocation
    if path == '/invoke' and method == 'POST':
        return handle_invoke(body)
    
    # Load test
    if path == '/load-test' and method == 'POST':
        return handle_load_test(body, context)
    
    # Get load test results
    if path.startswith('/load-test/') and method == 'GET':
        test_id = path.split('/')[-1]
        return get_load_test_results(test_id)
    
    # Sustained load test
    if path == '/sustained-load' and method == 'POST':
        return handle_sustained_load(body)
    
    # Get sustained load stats
    if path.startswith('/sustained-load/') and method == 'GET':
        test_id = path.split('/')[-1]
        return handle_get_stats(test_id)
    
    # Stop sustained load
    if path.startswith('/sustained-load/') and method == 'DELETE':
        test_id = path.split('/')[-1]
        return handle_stop_test(test_id)
    
    return respond(404, {'error': 'Not found'})

def handle_invoke(body):
    """Handle single agent invocation"""
    # Accept either agent name or agentArn for backward compatibility
    agent_name = body.get('agent', '').lower()
    agent_arn = body.get('agentArn')
    prompt = body.get('prompt', 'Hello')
    
    # If agent name provided, look up ARN from environment
    if agent_name and not agent_arn:
        if agent_name == 'max':
            # Max uses Fargate via API Gateway proxy
            agent_arn = os.environ.get('MAX_FARGATE_URL', '')
        else:
            # Other agents use AgentCore Runtime ARN
            agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    
    if not agent_arn:
        return respond(400, {'error': 'agent or agentArn required'})
    
    try:
        start_time = time.time()
        
        # Check if this is a Fargate URL (starts with http)
        if agent_arn.startswith('http'):
            # For Fargate (Max agent), make HTTP request
            import urllib3
            http = urllib3.PoolManager()
            
            fargate_response = http.request(
                'POST',
                agent_arn,
                body=json.dumps({
                    'prompt': prompt,
                    'customerId': 'cust_matthewnguyen22',
                    'sessionId': f'load-test-{int(time.time() * 1000)}'
                }),
                headers={'Content-Type': 'application/json'}
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            result_data = json.loads(fargate_response.data.decode('utf-8'))
            
            return respond(200, {
                'success': True,
                'response': result_data.get('response', str(result_data)),
                'duration_ms': duration_ms
            })
        
        # For AgentCore Runtime agents - use same pattern as agent-lambda
        # Prepare payload with consistent customer_id format
        payload = {
            'prompt': prompt,
            'customer_id': 'cust_matthewnguyen22',
            'sessionId': str(uuid.uuid4()),
            'userId': 'cust_matthewnguyen22'
        }
        
        # Encode payload
        encoded_payload = json.dumps(payload).encode('utf-8')
        
        # Invoke AgentCore Runtime (same as agent-lambda)
        response = bedrock_agentcore.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            qualifier='DEFAULT',
            runtimeSessionId=str(uuid.uuid4()),
            runtimeUserId='cust_matthewnguyen22',
            payload=encoded_payload,
            contentType='application/json'
        )
        
        # Parse response (same as agent-lambda)
        result_text = ""
        if response.get("contentType") == "application/json":
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                result_text = response_data
            else:
                result_text = str(response.get('response', ''))
        else:
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                result_text = response_data
            else:
                result_text = str(response.get('response', ''))
        
        duration = time.time() - start_time
        
        return respond(200, {
            'success': True,
            'response': result_text,
            'duration_ms': int(duration * 1000)
        })
        
    except Exception as e:
        return respond(500, {
            'success': False,
            'error': str(e)
        })

def handle_load_test(body, context=None):
    """Handle parallel load test with async support"""
    agent_name = body.get('agent', '').lower()
    agent_arn = body.get('agentArn')
    num_requests = body.get('numRequests', 10)
    prompt = body.get('prompt', 'Hello')
    async_mode = body.get('async', True)  # Default to async mode
    
    # If agent name provided, look up ARN from environment
    if agent_name and not agent_arn:
        if agent_name == 'max':
            # Max uses Fargate via API Gateway proxy
            agent_arn = os.environ.get('MAX_FARGATE_URL', '')
        else:
            # Other agents use AgentCore Runtime ARN
            agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    
    if not agent_arn:
        return respond(400, {'error': 'agent or agentArn required'})
    
    # Generate unique test ID
    test_id = str(uuid.uuid4())
    
    # If async mode, invoke Lambda asynchronously and return immediately
    if async_mode:
        # Store initial test status in DynamoDB
        try:
            table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
            table.put_item(Item={
                'test_id': test_id,
                'status': 'running',
                'agent_name': agent_name,
                'num_requests': num_requests,
                'completed': 0,
                'successful': 0,
                'failed': 0,
                'durations': [],
                'errors': [],
                'created_at': datetime.now().isoformat(),
                'ttl': int(time.time()) + 3600  # Expire after 1 hour
            })
        except Exception as e:
            print(f"Error storing test status: {e}")
        
        # Invoke this Lambda asynchronously to process the test
        # Note: context is passed from lambda_handler
        try:
            function_name = context.function_name if hasattr(context, 'function_name') else 'genai_petstore_load_tester_lambda'
            lambda_client.invoke(
                FunctionName=function_name,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps({
                    'action': 'process_load_test',
                    'test_id': test_id,
                    'agent_name': agent_name,
                    'agent_arn': agent_arn,
                    'num_requests': num_requests,
                    'prompt': prompt
                })
            )
        except Exception as e:
            print(f"Error invoking async Lambda: {e}")
            return respond(500, {'error': f'Failed to start async test: {str(e)}'})
        
        # Return immediately with test ID
        return respond(200, {
            'test_id': test_id,
            'status': 'started',
            'message': f'Load test started with {num_requests} requests. Use test_id to poll for results.'
        })
    
    # Synchronous mode (for backward compatibility or small tests)
    results = {
        'total': num_requests,
        'successful': 0,
        'failed': 0,
        'durations': [],
        'errors': []
    }
    
    is_fargate = agent_arn.startswith('http')
    
    # Run requests sequentially (Lambda has limited concurrency)
    # Limit to 3 requests for sync mode to stay under API Gateway timeout
    for i in range(min(num_requests, 3)):
        try:
            start_time = time.time()
            
            # Generate 33-char session ID (matches frontend JavaScript pattern)
            customer_id = 'cust_matthewnguyen22'
            session_id = get_load_test_session_id(customer_id, i)
            
            if is_fargate:
                # For Fargate (Max agent), make HTTP request
                import urllib3
                http = urllib3.PoolManager()
                
                fargate_response = http.request(
                    'POST',
                    agent_arn,
                    body=json.dumps({
                        'prompt': prompt,
                        'customerId': 'cust_matthewnguyen22',
                        'sessionId': session_id
                    }),
                    headers={'Content-Type': 'application/json'}
                )
            else:
                # For AgentCore Runtime agents - use same pattern as agent-lambda
                payload = {
                    'prompt': prompt,
                    'customer_id': 'cust_matthewnguyen22',
                    'sessionId': session_id,
                    'userId': 'cust_matthewnguyen22'
                }
                encoded_payload = json.dumps(payload).encode('utf-8')
                
                response = bedrock_agentcore.invoke_agent_runtime(
                    agentRuntimeArn=agent_arn,
                    qualifier='DEFAULT',
                    runtimeSessionId=session_id,
                    runtimeUserId='cust_matthewnguyen22',
                    payload=encoded_payload,
                    contentType='application/json'
                )
                
                # Just consume the response
                if hasattr(response.get('response'), 'read'):
                    response['response'].read()
            
            duration = time.time() - start_time
            results['durations'].append(duration * 1000)
            results['successful'] += 1
            
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(str(e))
    
    # Calculate stats
    if results['durations']:
        results['stats'] = {
            'avg_duration': sum(results['durations']) / len(results['durations']),
            'min_duration': min(results['durations']),
            'max_duration': max(results['durations'])
        }
    
    return respond(200, results)

def handle_sustained_load(body):
    """Handle sustained load test using async pattern"""
    agent_name = body.get('agent', '').lower()
    agent_arn = body.get('agentArn')
    tps = body.get('tps', 2)
    duration = body.get('duration', 60)
    test_id = body.get('test_id', str(uuid.uuid4()))
    prompt = body.get('prompt', 'Hello')
    
    # If agent name provided, look up ARN from environment
    if agent_name and not agent_arn:
        if agent_name == 'max':
            agent_arn = os.environ.get('MAX_FARGATE_URL', '')
        else:
            agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    
    if not agent_arn:
        return respond(400, {'error': 'agent or agentArn required'})
    
    # Calculate total requests based on TPS and duration
    num_requests = tps * duration
    
    # Store initial test status in DynamoDB
    try:
        table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
        table.put_item(Item={
            'test_id': test_id,
            'status': 'running',
            'agent_name': agent_name,
            'tps': tps,
            'duration': duration,
            'num_requests': num_requests,
            'completed': 0,
            'successful': 0,
            'failed': 0,
            'durations': [],
            'errors': [],
            'created_at': datetime.now().isoformat(),
            'ttl': int(time.time()) + 3600  # Expire after 1 hour
        })
    except Exception as e:
        print(f"Error storing test status: {e}")
    
    # Invoke this Lambda asynchronously to process the test
    try:
        function_name = 'genai_petstore_load_tester_lambda'  # Default name
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps({
                'action': 'process_load_test',
                'test_id': test_id,
                'agent_name': agent_name,
                'agent_arn': agent_arn,
                'num_requests': num_requests,
                'prompt': prompt
            })
        )
    except Exception as e:
        print(f"Error invoking async Lambda: {e}")
        return respond(500, {'error': f'Failed to start sustained test: {str(e)}'})
    
    return respond(200, {
        'test_id': test_id,
        'status': 'started',
        'tps': tps,
        'duration': duration,
        'message': f'Sustained load test started: {tps} TPS for {duration} seconds ({num_requests} total requests)'
    })

def handle_get_stats(test_id):
    """Get sustained load test stats with calculated metrics"""
    try:
        table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
        response = table.get_item(Key={'test_id': test_id})
        
        if 'Item' not in response:
            return respond(404, {'error': 'Test not found'})
        
        item = response['Item']
        
        # Convert Decimal to float/int for JSON serialization
        item = decimal_to_float(item)
        
        # Calculate additional metrics for live stats display
        completed = item.get('completed', 0)
        successful = item.get('successful', 0)
        failed = item.get('failed', 0)
        num_requests = item.get('num_requests', 0)
        durations = item.get('durations', [])
        
        # Calculate success rate
        total_completed = successful + failed
        success_rate = (successful / total_completed * 100) if total_completed > 0 else 0
        
        # Calculate average response time (in seconds)
        avg_response_time = (sum(durations) / len(durations) / 1000) if durations else 0
        
        # Calculate actual TPS (if test is running)
        created_at = item.get('created_at')
        actual_tps = 0
        if created_at and item.get('status') == 'running':
            try:
                start_time = datetime.fromisoformat(created_at)
                elapsed_seconds = (datetime.now() - start_time).total_seconds()
                if elapsed_seconds > 0:
                    actual_tps = completed / elapsed_seconds
            except:
                pass
        
        # Return data in format expected by frontend
        return respond(200, {
            'test_id': item.get('test_id'),
            'status': item.get('status'),
            'agent_name': item.get('agent_name'),
            'total_requests': num_requests,
            'completed': completed,
            'successful': successful,
            'failed': failed,
            'actual_tps': actual_tps,
            'avg_response_time': avg_response_time,
            'success_rate': success_rate,
            'durations': durations,
            'errors': item.get('errors', []),
            'stats': item.get('stats', {}),
            'created_at': item.get('created_at'),
            'completed_at': item.get('completed_at'),
            'stopped_at': item.get('stopped_at')
        })
        
    except Exception as e:
        return respond(500, {'error': f'Failed to get stats: {str(e)}'})

def handle_stop_test(test_id):
    """Stop sustained load test (mark as stopped in DynamoDB)"""
    try:
        table = dynamodb.Table(LOAD_TEST_RESULTS_TABLE)
        
        # Check if test exists
        response = table.get_item(Key={'test_id': test_id})
        if 'Item' not in response:
            return respond(404, {'error': 'Test not found'})
        
        # Mark as stopped
        table.update_item(
            Key={'test_id': test_id},
            UpdateExpression='SET #status = :status, stopped_at = :stopped_at',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'stopped',
                ':stopped_at': datetime.now().isoformat()
            }
        )
        
        return respond(200, {
            'message': f'Test {test_id} marked as stopped. Background processing may continue briefly.'
        })
    except Exception as e:
        return respond(500, {'error': f'Failed to stop test: {str(e)}'})

def respond(status_code, body):
    """Create HTTP response with comprehensive CORS headers"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS,DELETE'
        },
        'body': json.dumps(body)
    }
