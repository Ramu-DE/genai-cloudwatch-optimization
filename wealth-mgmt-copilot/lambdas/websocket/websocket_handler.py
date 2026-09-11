import json
import boto3
import os
import time
import logging
from datetime import datetime
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get('REGION', 'us-west-2')
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE', 'wealth_mgmt_websocket_connections')

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
connections_table = dynamodb.Table(CONNECTIONS_TABLE)


def lambda_handler(event, context):
    route_key = event.get('requestContext', {}).get('routeKey', '$default')
    connection_id = event.get('requestContext', {}).get('connectionId', '')
    domain = event.get('requestContext', {}).get('domainName', '')
    stage = event.get('requestContext', {}).get('stage', '')

    logger.info(f"WebSocket: route={route_key} connection={connection_id}")

    if route_key == '$connect':
        return handle_connect(connection_id, event)
    elif route_key == '$disconnect':
        return handle_disconnect(connection_id)
    elif route_key == 'sendMessage':
        return handle_message(connection_id, event, domain, stage)
    else:
        return handle_message(connection_id, event, domain, stage)


def handle_connect(connection_id, event):
    """Handle new WebSocket connection"""
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        client_id = query_params.get('client_id', 'anonymous')

        connections_table.put_item(Item={
            'connectionId': connection_id,
            'client_id': client_id,
            'connected_at': datetime.now().isoformat(),
            'ttl': int(time.time()) + 7200
        })

        logger.info(f"Connected: {connection_id} (client: {client_id})")
        return {'statusCode': 200}

    except Exception as e:
        logger.error(f"Connect error: {e}")
        return {'statusCode': 500}


def handle_disconnect(connection_id):
    """Handle WebSocket disconnection"""
    try:
        connections_table.delete_item(Key={'connectionId': connection_id})
        logger.info(f"Disconnected: {connection_id}")
        return {'statusCode': 200}
    except Exception as e:
        logger.error(f"Disconnect error: {e}")
        return {'statusCode': 500}


def handle_message(connection_id, event, domain, stage):
    """Handle incoming WebSocket message — route to agent"""
    try:
        body = json.loads(event.get('body', '{}'))
        agent_name = body.get('agent', '').lower()
        message = body.get('message', '')
        client_id = body.get('client_id', 'anonymous')
        session_id = body.get('session_id', '')

        if agent_name not in ['marcus', 'sophia', 'olivia', 'victor']:
            send_to_connection(domain, stage, connection_id, {
                'type': 'error',
                'message': f'Invalid agent: {agent_name}'
            })
            return {'statusCode': 400}

        send_to_connection(domain, stage, connection_id, {
            'type': 'status',
            'message': f'Routing to {agent_name.title()}...',
            'agent': agent_name
        })

        agent_arn = os.environ.get(f'{agent_name.upper()}_AGENT_ARN')
        if not agent_arn:
            send_to_connection(domain, stage, connection_id, {
                'type': 'error',
                'message': f'Agent {agent_name} not configured'
            })
            return {'statusCode': 500}

        agentcore_client = boto3.client('bedrock-agentcore', region_name=AWS_REGION)

        payload = {
            'prompt': message,
            'client_id': client_id,
            'customer_id': client_id,
            'timestamp': datetime.now().isoformat(),
            'agent': agent_name,
            'sessionId': session_id,
            'userId': client_id
        }

        start_time = time.time()

        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=agent_arn,
            qualifier='DEFAULT',
            runtimeSessionId=session_id or f"ws_{connection_id[:20]}",
            runtimeUserId=client_id,
            payload=json.dumps(payload).encode('utf-8'),
            contentType='application/json'
        )

        duration = time.time() - start_time

        agent_response = ""
        if hasattr(response.get('response'), 'read'):
            response_data = response['response'].read()
            if isinstance(response_data, bytes):
                response_data = response_data.decode('utf-8')
            agent_response = response_data
        else:
            agent_response = str(response.get('response', ''))

        send_to_connection(domain, stage, connection_id, {
            'type': 'response',
            'agent': agent_name,
            'message': agent_response,
            'duration_ms': round(duration * 1000),
            'session_id': session_id
        })

        return {'statusCode': 200}

    except Exception as e:
        logger.error(f"Message handling error: {e}")
        try:
            send_to_connection(domain, stage, connection_id, {
                'type': 'error',
                'message': f'Error processing request: {str(e)}'
            })
        except Exception:
            pass
        return {'statusCode': 500}


def send_to_connection(domain, stage, connection_id, data):
    """Send message back to WebSocket client"""
    endpoint_url = f"https://{domain}/{stage}"
    apigw = boto3.client(
        'apigatewaymanagementapi',
        endpoint_url=endpoint_url,
        region_name=AWS_REGION
    )

    try:
        apigw.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode('utf-8')
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'GoneException':
            logger.info(f"Stale connection removed: {connection_id}")
            try:
                connections_table.delete_item(Key={'connectionId': connection_id})
            except Exception:
                pass
        else:
            raise
