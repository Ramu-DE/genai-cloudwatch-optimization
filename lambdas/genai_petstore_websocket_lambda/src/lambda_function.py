#!/usr/bin/env python3
"""
WebSocket Lambda Handler for GenAI Pet Store
Handles WebSocket connections and agent communication
"""

import json
import os
import boto3
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# AWS clients
dynamodb = boto3.resource('dynamodb')
bedrock_agentcore = boto3.client('bedrock-agentcore')
apigateway_management = None  # Initialized per request

# Environment variables
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE', 'genai_petstore_websocket_connections')
BELLA_AGENT_ARN = os.environ.get('BELLA_AGENT_ARN')
OLIVER_AGENT_ARN = os.environ.get('OLIVER_AGENT_ARN')
LUNA_AGENT_ARN = os.environ.get('LUNA_AGENT_ARN')
MAX_AGENT_ARN = os.environ.get('MAX_AGENT_ARN')

AGENT_ARNS = {
    'bella': BELLA_AGENT_ARN,
    'oliver': OLIVER_AGENT_ARN,
    'luna': LUNA_AGENT_ARN,
    'max': MAX_AGENT_ARN
}


def lambda_handler(event, context):
    """Main Lambda handler for WebSocket events"""
    
    logger.info(f"📨 WebSocket Event: {json.dumps(event)}")
    
    route_key = event.get('requestContext', {}).get('routeKey')
    connection_id = event.get('requestContext', {}).get('connectionId')
    domain_name = event.get('requestContext', {}).get('domainName')
    stage = event.get('requestContext', {}).get('stage')
    
    # Initialize API Gateway Management API client
    global apigateway_management
    apigateway_management = boto3.client(
        'apigatewaymanagementapi',
        endpoint_url=f'https://{domain_name}/{stage}'
    )
    
    try:
        if route_key == '$connect':
            return handle_connect(connection_id, event)
        elif route_key == '$disconnect':
            return handle_disconnect(connection_id)
        elif route_key == 'sendMessage':
            # Direct route from API Gateway route selection expression
            return handle_message(connection_id, event)
        elif route_key == '$default':
            # Parse action from message body
            body = event.get('body', '{}')
            if isinstance(body, str):
                body = json.loads(body)
            action = body.get('action')
            
            if action == 'sendMessage':
                return handle_message(connection_id, event)
            else:
                logger.warning(f"Unknown action: {action}")
                send_error(connection_id, f"Unknown action: {action}")
                return {'statusCode': 400, 'body': f'Unknown action: {action}'}
        else:
            logger.warning(f"Unknown route: {route_key}")
            return {'statusCode': 400, 'body': 'Unknown route'}
            
    except Exception as e:
        logger.error(f"❌ Error handling WebSocket event: {e}", exc_info=True)
        send_error(connection_id, str(e))
        return {'statusCode': 500, 'body': str(e)}


def handle_connect(connection_id, event):
    """Handle new WebSocket connection"""
    logger.info(f"🔌 New connection: {connection_id}")
    
    try:
        # Store connection in DynamoDB
        table = dynamodb.Table(CONNECTIONS_TABLE)
        table.put_item(
            Item={
                'connectionId': connection_id,
                'connectedAt': datetime.utcnow().isoformat(),
                'ttl': int(datetime.utcnow().timestamp()) + 7200  # 2 hours TTL
            }
        )
        
        logger.info(f"✅ Connection stored: {connection_id}")
        return {'statusCode': 200, 'body': 'Connected'}
        
    except Exception as e:
        logger.error(f"❌ Error storing connection: {e}")
        return {'statusCode': 500, 'body': str(e)}


def handle_disconnect(connection_id):
    """Handle WebSocket disconnection"""
    logger.info(f"🔌 Disconnection: {connection_id}")
    
    try:
        # Remove connection from DynamoDB
        table = dynamodb.Table(CONNECTIONS_TABLE)
        table.delete_item(Key={'connectionId': connection_id})
        
        logger.info(f"✅ Connection removed: {connection_id}")
        return {'statusCode': 200, 'body': 'Disconnected'}
        
    except Exception as e:
        logger.error(f"❌ Error removing connection: {e}")
        return {'statusCode': 500, 'body': str(e)}


def handle_message(connection_id, event):
    """Handle incoming message from client"""
    logger.info(f"💬 Message from {connection_id}")
    
    try:
        # Parse message body
        body = json.loads(event.get('body', '{}'))
        agent = body.get('agent', 'bella')
        message = body.get('message', '')
        customer_id = body.get('customer_id', 'unknown')
        session_id = body.get('session_id', connection_id)
        
        logger.info(f"📝 Agent: {agent}, Customer: {customer_id}, Session: {session_id}")
        logger.info(f"📝 Message: {message[:100]}...")
        
        # Send acknowledgment
        send_to_client(connection_id, {
            'type': 'acknowledgment',
            'message': 'Message received, processing...'
        })
        
        # Invoke agent
        agent_arn = AGENT_ARNS.get(agent)
        if not agent_arn:
            raise ValueError(f"Unknown agent: {agent}")
        
        logger.info(f"🤖 Invoking agent: {agent_arn}")
        
        # Prepare payload (same format as agent-lambda)
        payload = {
            'prompt': message,
            'customer_id': customer_id,
            'timestamp': datetime.utcnow().isoformat(),
            'agent': agent,
            'sessionId': session_id,
            'userId': customer_id
        }
        
        # Encode payload
        encoded_payload = json.dumps(payload).encode('utf-8')
        
        # Get X-Ray trace context for proper propagation
        trace_header = os.environ.get('_X_AMZN_TRACE_ID', '')
        
        # Parse X-Ray trace header: Root=1-xxx-yyy;Parent=zzz;Sampled=1
        trace_id = ''
        trace_parent = ''
        if trace_header:
            parts = trace_header.split(';')
            for part in parts:
                if part.startswith('Root='):
                    trace_id = part.split('=')[1]
                elif part.startswith('Parent='):
                    trace_parent = part.split('=')[1]
        
        logger.info(f"📍 ===== X-RAY TRACE CONTEXT =====")
        logger.info(f"📍 Full Trace Header: {trace_header}")
        logger.info(f"📍 Trace ID (Root): {trace_id}")
        logger.info(f"📍 Trace Parent: {trace_parent}")
        logger.info(f"📍 Passing to AgentCore for trace propagation")
        logger.info(f"📍 ================================")
        
        # Build invocation params
        invoke_params = {
            'agentRuntimeArn': agent_arn,
            'qualifier': 'DEFAULT',
            'runtimeSessionId': session_id,
            'runtimeUserId': customer_id,
            'payload': encoded_payload,
            'contentType': 'application/json'
        }
        
        # Add X-Ray trace propagation if available
        if trace_id:
            invoke_params['traceId'] = trace_id
        if trace_parent:
            invoke_params['traceParent'] = trace_parent
        if trace_header:
            invoke_params['traceState'] = trace_header
        
        # Invoke AgentCore with trace propagation
        response = bedrock_agentcore.invoke_agent_runtime(**invoke_params)
        
        logger.info(f"📍 Response received from AgentCore")
        logger.info(f"📍 Trace propagation complete")
        
        # Parse response (same as agent-lambda)
        agent_response = ""
        
        if response.get("contentType") == "application/json":
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                agent_response = response_data
            else:
                agent_response = str(response.get('response', ''))
        else:
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                agent_response = response_data
            else:
                agent_response = str(response.get('response', ''))
        
        # Send complete response to client
        send_to_client(connection_id, {
            'type': 'complete',
            'response': agent_response
        })
        
        logger.info(f"✅ Agent response sent to {connection_id}")
        return {'statusCode': 200, 'body': 'Message processed'}
        
    except Exception as e:
        logger.error(f"❌ Error processing message: {e}", exc_info=True)
        
        # Send error to client
        try:
            send_to_client(connection_id, {
                'type': 'error',
                'message': str(e)
            })
        except:
            pass
        
        return {'statusCode': 500, 'body': str(e)}


def send_to_client(connection_id, data):
    """Send data to WebSocket client"""
    try:
        apigateway_management.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data).encode('utf-8')
        )
        logger.info(f"📤 Sent to client: {data.get('type', 'unknown')}")
    except apigateway_management.exceptions.GoneException:
        logger.warning(f"⚠️ Connection gone: {connection_id}")
        # Clean up stale connection
        try:
            table = dynamodb.Table(CONNECTIONS_TABLE)
            table.delete_item(Key={'connectionId': connection_id})
        except:
            pass
    except Exception as e:
        logger.error(f"❌ Error sending to client: {e}")
        raise


def send_error(connection_id, error_message):
    """Send error message to WebSocket client"""
    try:
        send_to_client(connection_id, {
            'type': 'error',
            'error': error_message
        })
    except Exception as e:
        logger.error(f"❌ Failed to send error to client: {e}")
