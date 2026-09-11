import json
import boto3
import uuid
import time
import os
import re
import logging
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Memory is managed by individual agents (Bella, Luna, Oliver, Max)
# Lambda only routes requests to agents - no memory management here

def get_customer_session_id(customer_id, agent_name):
    """Generate deterministic session ID for customer-agent pair"""
    import hashlib
    
    # Create deterministic session based on customer + agent
    base = f"{customer_id}_{agent_name}"
    hash_hex = hashlib.md5(base.encode()).hexdigest()
    
    # Create 33-char session ID (AgentCore compliant - minimum 33 chars)
    session_id = f"chat_{hash_hex[:28]}"  # 5 + 28 = 33 chars
    return session_id

def map_username_to_customer_id(raw_customer_id, region):
    """Map username to actual customer_id by looking up in auth table"""
    if not raw_customer_id or raw_customer_id == 'anonymous':
        return 'anonymous'
    
    # If it already looks like a customer ID (starts with 'cust'), return as-is
    if raw_customer_id.startswith('cust'):
        print(f"ℹ️ Already a customer ID: {raw_customer_id}")
        return raw_customer_id
    
    try:
        # Initialize DynamoDB client
        dynamodb = boto3.client('dynamodb', region_name=region)
        
        # Look up username in auth table
        table_name = os.environ.get('CUSTOMER_PROFILES_TABLE', 'genai_petstore_user_auth')
        
        try:
            response = dynamodb.get_item(
                TableName=table_name,
                Key={'email': {'S': raw_customer_id}}
            )
            
            if 'Item' in response:
                actual_customer_id = response['Item'].get('customer_id', {}).get('S', raw_customer_id)
                print(f"✅ Username mapping found: {raw_customer_id} → {actual_customer_id}")
                return actual_customer_id
        except Exception as e:
            print(f"⚠️ Could not lookup in auth table: {e}")
        
        # Fallback: return as-is
        print(f"ℹ️ Using username as customer ID: {raw_customer_id}")
        return raw_customer_id
        
    except Exception as e:
        print(f"❌ Error mapping username to customer_id: {e}")
        return raw_customer_id

def lambda_handler(event, context):
    print("=" * 80)
    print("🚀 LAMBDA INVOCATION START")
    print(f"📋 Request ID: {context.aws_request_id if context else 'N/A'}")
    print(f"📋 Trace ID: {os.environ.get('_X_AMZN_TRACE_ID', 'N/A')}")
    print(f"📋 HTTP Method: {event.get('httpMethod', 'N/A')}")
    print("=" * 80)
    
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        print("🔧 Handling CORS preflight request")
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
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        # Extract parameters
        agent_name = body.get('agent', '').lower()
        message = body.get('message', '')
        customer_id = body.get('customer_id', 'anonymous')
        
        # Accept session_id from browser (try both formats)
        browser_session_id = body.get('session_id') or body.get('sessionId')
        
        # Validate agent name
        if agent_name not in ['bella', 'luna', 'oliver', 'max']:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
                },
                'body': json.dumps({'error': f'Invalid agent: {agent_name}'})
            }
        
        # Get agent ARN from environment
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
        
        # Initialize AgentCore client
        region = os.environ.get('REGION', 'us-west-2')
        client = boto3.client('bedrock-agentcore', region_name=region)
        
        # Generate request ID
        request_id = f'req-{int(time.time())}'
        
        # Map customer ID first
        user_id = map_username_to_customer_id(customer_id, region)
        
        # Use browser's session_id if provided, otherwise generate one
        if browser_session_id:
            session_id = browser_session_id
            print(f"🔧 Using browser session ID: {session_id}")
        else:
            session_id = get_customer_session_id(user_id, agent_name)
            print(f"🔧 Generated fallback session ID: {session_id}")
        
        print(f"📝 Message: {message[:100]}...")
        print("-" * 80)
        
        # Prepare payload for AgentCore
        payload = {
            'prompt': message,
            'customer_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'requestId': request_id,
            'agent': agent_name,
            'sessionId': session_id,
            'userId': user_id
        }
        
        # Encode payload
        encoded_payload = json.dumps(payload).encode('utf-8')
        
        print("📦 AGENTCORE PAYLOAD PREPARATION")
        print("-" * 40)
        print(f"📦 Payload Size: {len(encoded_payload)} bytes")
        
        # Invoke AgentCore agent
        print("�  AGENTCORE INVOCATION")
        print("-" * 80)
        
        start_time = time.time()
        
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
        
        print(f"📍 ===== X-RAY TRACE CONTEXT =====")
        print(f"📍 Full Trace Header: {trace_header}")
        print(f"📍 Trace ID (Root): {trace_id}")
        print(f"📍 Trace Parent: {trace_parent}")
        print(f"📍 Passing to AgentCore for trace propagation")
        print(f"📍 ================================")
        
        invocation_params = {
            'agentRuntimeArn': agent_arn,
            'qualifier': 'DEFAULT',
            'runtimeSessionId': session_id,
            'runtimeUserId': user_id,
            'payload': encoded_payload,
            'contentType': 'application/json'
        }
        
        # Add X-Ray trace propagation if available
        if trace_id:
            invocation_params['traceId'] = trace_id
        if trace_parent:
            invocation_params['traceParent'] = trace_parent
        if trace_header:
            invocation_params['traceState'] = trace_header
        
        print(f"📦 Invocation params: {list(invocation_params.keys())}")
        
        response = client.invoke_agent_runtime(**invocation_params)
        
        print(f"📍 Response received from AgentCore")
        print(f"📍 Trace propagation complete")
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"✅ AgentCore invocation successful in {duration:.2f} seconds")
        print("-" * 80)
        
        # Parse AgentCore response
        agent_response = ""
        
        if response.get("contentType") == "application/json":
            print("📥 Processing JSON response format")
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                agent_response = response_data
            else:
                agent_response = str(response.get('response', ''))
        else:
            print("📥 Processing non-JSON response format")
            if hasattr(response.get('response'), 'read'):
                response_data = response['response'].read()
                if isinstance(response_data, bytes):
                    response_data = response_data.decode('utf-8')
                agent_response = response_data
            else:
                agent_response = str(response.get('response', ''))
        
        print("📊 FINAL RESULTS")
        print("=" * 80)
        print(f"🤖 Agent Response: {json.dumps(agent_response)}")
        print(f"📊 Response length: {len(agent_response)} characters")
        print(f"� Se ssion ID: {session_id}")
        print(f"👤 User ID: {user_id}")
        print("=" * 80)
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS, GET',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amzn-Trace-Id',
                'Access-Control-Expose-Headers': 'X-Amzn-Trace-Id,X-Amzn-RequestId'
            },
            'body': json.dumps({
                'agent': agent_name,
                'response': agent_response,
                'customer_id': user_id,
                'session_id': session_id,
                'trace_id': context.aws_request_id if context else None
            })
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS, GET',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Amzn-Trace-Id',
                'Access-Control-Expose-Headers': 'X-Amzn-Trace-Id,X-Amzn-RequestId'
            },
            'body': json.dumps({
                'error': str(e),
                'trace_id': context.aws_request_id if context else None
            })
        } 