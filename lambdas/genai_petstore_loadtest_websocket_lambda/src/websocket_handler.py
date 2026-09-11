"""
WebSocket Handler for Load Tester
Handles real-time load test execution with progress updates
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
apigatewaymanagementapi = None  # Will be initialized per connection

# DynamoDB table for storing load test results
LOAD_TEST_RESULTS_TABLE = os.environ.get('LOAD_TEST_RESULTS_TABLE', 'genai_petstore_load_test_results')

def get_load_test_session_id(customer_id, request_index):
    """Generate 33-char session ID for load testing"""
    import hashlib
    
    customer_name = customer_id.replace('cust_', '') if customer_id.startswith('cust_') else customer_id
    timestamp_ms = int(time.time() * 1000)
    random_base = f"{timestamp_ms}_{request_index}"
    random_hex = hashlib.md5(random_base.encode()).hexdigest()[:13]
    session_id = f"cust_{customer_name}_{random_hex}"
    
    if len(session_id) > 33:
        session_id = session_id[:33]
    
    return session_id

def send_to_connection(connection_id, data, domain_name, stage):
    """Send message to WebSocket connection"""
    global apigatewaymanagementapi
    
    if not apigatewaymanagementapi:
        endpoint_url = f"https://{domain_name}/{stage}"
        apigatewaymanagementapi = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=endpoint_url
        )
    
    try:
        apigatewaymanagementapi.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode('utf-8')
        )
        return True
    except apigatewaymanagementapi.exceptions.GoneException:
        print(f"Connection {connection_id} is gone")
        return False
    except Exception as e:
        print(f"Error sending to connection: {e}")
        return False

def handle_connect(event):
    """Handle WebSocket connection"""
    connection_id = event['requestContext']['connectionId']
    print(f"Client connected: {connection_id}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Connected'})
    }

def handle_disconnect(event):
    """Handle WebSocket disconnection"""
    connection_id = event['requestContext']['connectionId']
    print(f"Client disconnected: {connection_id}")
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Disconnected'})
    }

def handle_single_invoke(event, body):
    """Handle single agent invocation with real-time response"""
    connection_id = event['requestContext']['connectionId']
    domain_name = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    
    agent_name = body.get('agent', '').lower()
    agent_arn = body.get('agentArn')
    prompt = body.get('prompt', 'Hello')
    
    # Look up agent ARN if name provided
    if agent_name and not agent_arn:
        if agent_name == 'max':
            agent_arn = os.environ.get('MAX_FARGATE_URL', '')
        else:
            agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    
    if not agent_arn:
        send_to_connection(connection_id, {
            'type': 'error',
            'error': 'agent or agentArn required'
        }, domain_name, stage)
        return {'statusCode': 200}
    
    # Send starting message
    send_to_connection(connection_id, {
        'type': 'invoke_start',
        'agent': agent_name
    }, domain_name, stage)
    
    try:
        start_time = time.time()
        
        # Check if Fargate URL
        if agent_arn.startswith('http'):
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
            
            send_to_connection(connection_id, {
                'type': 'invoke_complete',
                'success': True,
                'response': result_data.get('response', str(result_data)),
                'duration_ms': duration_ms
            }, domain_name, stage)
        else:
            # AgentCore Runtime
            payload = {
                'prompt': prompt,
                'customer_id': 'cust_matthewnguyen22',
                'sessionId': str(uuid.uuid4()),
                'userId': 'cust_matthewnguyen22'
            }
            encoded_payload = json.dumps(payload).encode('utf-8')
            
            response = bedrock_agentcore.invoke_agent_runtime(
                agentRuntimeArn=agent_arn,
                qualifier='DEFAULT',
                runtimeSessionId=str(uuid.uuid4()),
                runtimeUserId='cust_matthewnguyen22',
                payload=encoded_payload,
                contentType='application/json'
            )
            
            # Parse response
            result_text = ""
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                result_text = response_data
            else:
                result_text = str(response.get('response', ''))
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            send_to_connection(connection_id, {
                'type': 'invoke_complete',
                'success': True,
                'response': result_text,
                'duration_ms': duration_ms
            }, domain_name, stage)
    
    except Exception as e:
        send_to_connection(connection_id, {
            'type': 'error',
            'error': str(e)
        }, domain_name, stage)
    
    return {'statusCode': 200}

def handle_load_test(event, body):
    """Handle parallel load test with real-time progress updates"""
    connection_id = event['requestContext']['connectionId']
    domain_name = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    
    agent_name = body.get('agent', '').lower()
    agent_arn = body.get('agentArn')
    num_requests = body.get('numRequests', 10)
    prompt = body.get('prompt', 'Hello')
    
    # Look up agent ARN if name provided
    if agent_name and not agent_arn:
        if agent_name == 'max':
            agent_arn = os.environ.get('MAX_FARGATE_URL', '')
        else:
            agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    
    if not agent_arn:
        send_to_connection(connection_id, {
            'type': 'error',
            'error': 'agent or agentArn required'
        }, domain_name, stage)
        return {'statusCode': 200}
    
    test_id = str(uuid.uuid4())
    
    # Send test started message
    send_to_connection(connection_id, {
        'type': 'load_test_start',
        'test_id': test_id,
        'num_requests': num_requests,
        'agent': agent_name
    }, domain_name, stage)
    
    results = {
        'successful': 0,
        'failed': 0,
        'durations': [],
        'errors': []
    }
    
    is_fargate = agent_arn.startswith('http')
    
    # Run requests sequentially with progress updates
    for i in range(num_requests):
        try:
            start_time = time.time()
            
            # Generate session ID
            customer_id = 'cust_matthewnguyen22'
            session_id = get_load_test_session_id(customer_id, i)
            
            if is_fargate:
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
                
                if hasattr(response.get('response'), 'read'):
                    response['response'].read()
            
            duration = (time.time() - start_time) * 1000
            results['durations'].append(duration)
            results['successful'] += 1
            
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(str(e))
        
        # Send progress update
        send_to_connection(connection_id, {
            'type': 'load_test_progress',
            'test_id': test_id,
            'completed': i + 1,
            'total': num_requests,
            'successful': results['successful'],
            'failed': results['failed']
        }, domain_name, stage)
    
    # Calculate final stats
    if results['durations']:
        stats = {
            'avg_duration': sum(results['durations']) / len(results['durations']),
            'min_duration': min(results['durations']),
            'max_duration': max(results['durations'])
        }
    else:
        stats = {}
    
    # Send completion message
    send_to_connection(connection_id, {
        'type': 'load_test_complete',
        'test_id': test_id,
        'num_requests': num_requests,
        'successful': results['successful'],
        'failed': results['failed'],
        'stats': stats,
        'errors': results['errors']
    }, domain_name, stage)
    
    return {'statusCode': 200}

def handle_sustained_load(event, body):
    """Handle sustained load test with real-time updates"""
    connection_id = event['requestContext']['connectionId']
    domain_name = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    
    agent_name = body.get('agent', '').lower()
    agent_arn = body.get('agentArn')
    tps = body.get('tps', 2)
    duration = body.get('duration', 60)
    prompt = body.get('prompt', 'Hello')
    
    # Look up agent ARN if name provided
    if agent_name and not agent_arn:
        if agent_name == 'max':
            agent_arn = os.environ.get('MAX_FARGATE_URL', '')
        else:
            agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN', '')
    
    if not agent_arn:
        send_to_connection(connection_id, {
            'type': 'error',
            'error': 'agent or agentArn required'
        }, domain_name, stage)
        return {'statusCode': 200}
    
    test_id = str(uuid.uuid4())
    num_requests = tps * duration
    
    # Send test started message
    send_to_connection(connection_id, {
        'type': 'sustained_test_start',
        'test_id': test_id,
        'tps': tps,
        'duration': duration,
        'num_requests': num_requests,
        'agent': agent_name
    }, domain_name, stage)
    
    results = {
        'successful': 0,
        'failed': 0,
        'durations': [],
        'errors': []
    }
    
    is_fargate = agent_arn.startswith('http')
    start_time = time.time()
    interval = 1.0 / tps  # Time between requests
    
    # Run requests with TPS throttling
    for i in range(num_requests):
        request_start = time.time()
        
        try:
            # Generate session ID
            customer_id = 'cust_matthewnguyen22'
            session_id = get_load_test_session_id(customer_id, i)
            
            if is_fargate:
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
                
                if hasattr(response.get('response'), 'read'):
                    response['response'].read()
            
            request_duration = (time.time() - request_start) * 1000
            results['durations'].append(request_duration)
            results['successful'] += 1
            
        except Exception as e:
            results['failed'] += 1
            results['errors'].append(str(e))
        
        # Send progress update every 5 requests or at end
        if (i + 1) % 5 == 0 or i == num_requests - 1:
            elapsed = time.time() - start_time
            actual_tps = (i + 1) / elapsed if elapsed > 0 else 0
            avg_response_time = sum(results['durations']) / len(results['durations']) if results['durations'] else 0
            
            send_to_connection(connection_id, {
                'type': 'sustained_test_progress',
                'test_id': test_id,
                'completed': i + 1,
                'total': num_requests,
                'successful': results['successful'],
                'failed': results['failed'],
                'actual_tps': round(actual_tps, 2),
                'avg_response_time': round(avg_response_time, 2),
                'elapsed_seconds': round(elapsed, 1)
            }, domain_name, stage)
        
        # Throttle to maintain TPS
        elapsed_request = time.time() - request_start
        sleep_time = max(0, interval - elapsed_request)
        if sleep_time > 0:
            time.sleep(sleep_time)
    
    # Calculate final stats
    total_elapsed = time.time() - start_time
    if results['durations']:
        stats = {
            'avg_duration': sum(results['durations']) / len(results['durations']),
            'min_duration': min(results['durations']),
            'max_duration': max(results['durations']),
            'actual_tps': num_requests / total_elapsed,
            'total_duration': total_elapsed
        }
    else:
        stats = {}
    
    # Send completion message
    send_to_connection(connection_id, {
        'type': 'sustained_test_complete',
        'test_id': test_id,
        'num_requests': num_requests,
        'successful': results['successful'],
        'failed': results['failed'],
        'stats': stats,
        'errors': results['errors'][:10]  # Limit errors to first 10
    }, domain_name, stage)
    
    return {'statusCode': 200}

def lambda_handler(event, context):
    """Main WebSocket Lambda handler"""
    route_key = event['requestContext']['routeKey']
    
    print(f"Route: {route_key}")
    
    # Handle connection lifecycle
    if route_key == '$connect':
        return handle_connect(event)
    
    if route_key == '$disconnect':
        return handle_disconnect(event)
    
    # Parse message body
    try:
        body = json.loads(event.get('body', '{}'))
    except:
        body = {}
    
    action = body.get('action', '')
    
    # Route to appropriate handler
    if action == 'invoke':
        return handle_single_invoke(event, body)
    elif action == 'loadTest':
        return handle_load_test(event, body)
    elif action == 'sustainedLoad':
        return handle_sustained_load(event, body)
    else:
        # Default route
        connection_id = event['requestContext']['connectionId']
        domain_name = event['requestContext']['domainName']
        stage = event['requestContext']['stage']
        
        send_to_connection(connection_id, {
            'type': 'error',
            'error': f'Unknown action: {action}'
        }, domain_name, stage)
        
        return {'statusCode': 200}
