import json
import boto3
import time
import os
import re
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cw_client = boto3.client('cloudwatch', region_name=os.environ.get('REGION', 'us-west-2'))

VALID_AGENTS = ['marcus', 'sophia', 'olivia', 'victor']

MAX_MESSAGE_LENGTH = 10000
MAX_CLIENT_ID_LENGTH = 64
CLIENT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_@.\-]+$')


def validate_input(body):
    """Validate and sanitize request input. Returns (cleaned_body, error_msg)."""
    agent_name = body.get('agent', '').lower().strip()
    message = body.get('message', '')
    client_id = body.get('client_id', body.get('customer_id', 'anonymous'))

    if not message or not message.strip():
        return None, 'Message cannot be empty'

    if len(message) > MAX_MESSAGE_LENGTH:
        return None, f'Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters'

    if client_id and client_id != 'anonymous':
        if len(client_id) > MAX_CLIENT_ID_LENGTH:
            return None, f'Client ID exceeds maximum length of {MAX_CLIENT_ID_LENGTH}'
        if not CLIENT_ID_PATTERN.match(client_id):
            return None, 'Client ID contains invalid characters'

    if agent_name == 'orchestrator':
        pass
    elif agent_name not in VALID_AGENTS:
        return None, f'Invalid agent: {agent_name}. Valid agents: {", ".join(VALID_AGENTS)}, orchestrator'

    return {
        'agent': agent_name,
        'message': message.strip(),
        'client_id': client_id,
        'session_id': body.get('session_id') or body.get('sessionId')
    }, None

def get_client_session_id(client_id, agent_name):
    """Generate deterministic session ID for client-agent pair"""
    import hashlib
    base = f"{client_id}_{agent_name}"
    hash_hex = hashlib.md5(base.encode()).hexdigest()
    session_id = f"chat_{hash_hex[:28]}"
    return session_id


def map_username_to_client_id(raw_client_id, region):
    """Map username to actual client_id by looking up in auth table"""
    if not raw_client_id or raw_client_id == 'anonymous':
        return 'anonymous'

    if raw_client_id.startswith('client'):
        return raw_client_id

    try:
        dynamodb = boto3.client('dynamodb', region_name=region)
        table_name = os.environ.get('USER_AUTH_TABLE', 'wealth_mgmt_user_auth')

        response = dynamodb.get_item(
            TableName=table_name,
            Key={'email': {'S': raw_client_id}}
        )

        if 'Item' in response:
            actual_client_id = response['Item'].get('client_id', {}).get('S', raw_client_id)
            print(f"Username mapping found: {raw_client_id} -> {actual_client_id}")
            return actual_client_id
    except Exception as e:
        print(f"Could not lookup in auth table: {e}")

    return raw_client_id


def invoke_single_agent(agent_name, message, user_id, session_id, region, trace_id, trace_parent, trace_header):
    """Invoke a single agent and return its response with timing."""
    agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN')
    if not agent_arn:
        return {'agent': agent_name, 'error': f'ARN not configured for {agent_name}', 'duration_ms': 0}

    client = boto3.client('bedrock-agentcore', region_name=region)
    request_id = f'req-{int(time.time())}-{agent_name}'
    agent_session_id = get_client_session_id(user_id, agent_name)

    payload = {
        'prompt': message,
        'customer_id': user_id,
        'client_id': user_id,
        'timestamp': datetime.now().isoformat(),
        'requestId': request_id,
        'agent': agent_name,
        'sessionId': agent_session_id,
        'userId': user_id
    }

    invocation_params = {
        'agentRuntimeArn': agent_arn,
        'qualifier': 'DEFAULT',
        'runtimeSessionId': agent_session_id,
        'runtimeUserId': user_id,
        'payload': json.dumps(payload).encode('utf-8'),
        'contentType': 'application/json'
    }
    if trace_id:
        invocation_params['traceId'] = trace_id
    if trace_parent:
        invocation_params['traceParent'] = trace_parent
    if trace_header:
        invocation_params['traceState'] = trace_header

    start = time.time()
    response = client.invoke_agent_runtime(**invocation_params)
    duration_ms = round((time.time() - start) * 1000)

    agent_response = ""
    if hasattr(response.get('response'), 'read'):
        data = response['response'].read()
        agent_response = data.decode('utf-8') if isinstance(data, bytes) else data
    else:
        agent_response = str(response.get('response', ''))

    return {'agent': agent_name, 'response': agent_response, 'duration_ms': duration_ms}


def orchestrate_agents(message, user_id, region, trace_id, trace_parent, trace_header, target_agents=None):
    """Fan out a request to multiple agents in parallel, collect and synthesize responses."""
    agents_to_query = target_agents or VALID_AGENTS
    results = []

    with ThreadPoolExecutor(max_workers=len(agents_to_query)) as executor:
        futures = {
            executor.submit(
                invoke_single_agent, name, message, user_id, None, region,
                trace_id, trace_parent, trace_header
            ): name
            for name in agents_to_query
        }
        for future in as_completed(futures):
            agent_name = futures[future]
            try:
                results.append(future.result())
            except Exception as e:
                results.append({'agent': agent_name, 'error': str(e), 'duration_ms': 0})

    return results


def lambda_handler(event, context):
    print("=" * 80)
    print("LAMBDA INVOCATION START - WEALTH MANAGEMENT AGENT ROUTER")
    print(f"Request ID: {context.aws_request_id if context else 'N/A'}")
    print(f"Trace ID: {os.environ.get('_X_AMZN_TRACE_ID', 'N/A')}")
    print(f"HTTP Method: {event.get('httpMethod', 'N/A')}")
    print("=" * 80)

    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS, GET',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amzn-Trace-Id',
                'Access-Control-Expose-Headers': 'X-Amzn-Trace-Id,X-Amzn-RequestId',
                'Access-Control-Max-Age': '86400'
            },
            'body': ''
        }

    try:
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        cleaned, error = validate_input(body)
        if error:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
                },
                'body': json.dumps({'error': error})
            }

        agent_name = cleaned['agent']
        message = cleaned['message']
        client_id = cleaned['client_id']
        browser_session_id = cleaned['session_id']

        region = os.environ.get('REGION', 'us-west-2')
        user_id = map_username_to_client_id(client_id, region)

        trace_header = os.environ.get('_X_AMZN_TRACE_ID', '')
        trace_id = ''
        trace_parent = ''
        if trace_header:
            parts = trace_header.split(';')
            for part in parts:
                if part.startswith('Root='):
                    trace_id = part.split('=')[1]
                elif part.startswith('Parent='):
                    trace_parent = part.split('=')[1]

        # Cross-agent orchestration mode
        if agent_name == 'orchestrator':
            print(f"Orchestrator mode: fanning out to all agents for client {user_id}")
            start_time = time.time()
            results = orchestrate_agents(message, user_id, region, trace_id, trace_parent, trace_header)
            total_duration = round((time.time() - start_time) * 1000)

            try:
                cw_client.put_metric_data(
                    Namespace='WealthMgmt/Agents',
                    MetricData=[{
                        'MetricName': 'OrchestratorLatency',
                        'Value': total_duration,
                        'Unit': 'Milliseconds',
                        'Dimensions': [{'Name': 'AgentCount', 'Value': str(len(results))}]
                    }]
                )
            except Exception:
                pass

            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                    'Access-Control-Expose-Headers': 'X-Amzn-Trace-Id,X-Amzn-RequestId',
                    'X-Amzn-Trace-Id': trace_header
                },
                'body': json.dumps({
                    'mode': 'orchestrator',
                    'agents': results,
                    'total_duration_ms': total_duration,
                    'client_id': user_id,
                    'trace_id': trace_id
                })
            }

        agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN')
        if not agent_arn:
            return {
                'statusCode': 500,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
                },
                'body': json.dumps({'error': f'Agent ARN not configured for {agent_name}'})
            }

        client = boto3.client('bedrock-agentcore', region_name=region)

        request_id = f'req-{int(time.time())}'

        if browser_session_id:
            session_id = browser_session_id
        else:
            session_id = get_client_session_id(user_id, agent_name)

        print(f"Agent: {agent_name} | Client: {user_id} | Session: {session_id}")
        print(f"Message: {message[:100]}...")

        payload = {
            'prompt': message,
            'customer_id': user_id,
            'client_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'requestId': request_id,
            'agent': agent_name,
            'sessionId': session_id,
            'userId': user_id
        }

        encoded_payload = json.dumps(payload).encode('utf-8')

        start_time = time.time()

        print(f"X-Ray Trace ID: {trace_id}")

        invocation_params = {
            'agentRuntimeArn': agent_arn,
            'qualifier': 'DEFAULT',
            'runtimeSessionId': session_id,
            'runtimeUserId': user_id,
            'payload': encoded_payload,
            'contentType': 'application/json'
        }

        if trace_id:
            invocation_params['traceId'] = trace_id
        if trace_parent:
            invocation_params['traceParent'] = trace_parent
        if trace_header:
            invocation_params['traceState'] = trace_header

        response = client.invoke_agent_runtime(**invocation_params)

        end_time = time.time()
        duration = end_time - start_time

        # Emit structured JSON log (EMF-compatible)
        print(json.dumps({
            'event': 'agent_invocation',
            'agent': agent_name,
            'client_id': user_id,
            'duration_ms': round(duration * 1000),
            'status': 'success',
            'session_id': session_id
        }))

        # Emit CloudWatch custom metrics
        try:
            cw_client.put_metric_data(
                Namespace='WealthMgmt/Agents',
                MetricData=[
                    {
                        'MetricName': 'RouterLatency',
                        'Value': duration * 1000,
                        'Unit': 'Milliseconds',
                        'Dimensions': [{'Name': 'AgentName', 'Value': agent_name}]
                    },
                    {
                        'MetricName': 'RouterInvocations',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [{'Name': 'AgentName', 'Value': agent_name}]
                    }
                ]
            )
        except Exception:
            pass

        agent_response = ""
        if hasattr(response.get('response'), 'read'):
            response_data = response['response'].read()
            if isinstance(response_data, bytes):
                response_data = response_data.decode('utf-8')
            agent_response = response_data
        else:
            agent_response = str(response.get('response', ''))

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Expose-Headers': 'X-Amzn-Trace-Id,X-Amzn-RequestId',
                'X-Amzn-Trace-Id': trace_header
            },
            'body': json.dumps({
                'response': agent_response,
                'agent': agent_name,
                'session_id': session_id,
                'request_id': request_id,
                'duration_ms': round(duration * 1000),
                'trace_id': trace_id
            })
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"AWS ClientError: {error_code} - {error_message}")
        return {
            'statusCode': 502,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'error': f'Agent invocation failed: {error_code}',
                'message': error_message
            })
        }

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
