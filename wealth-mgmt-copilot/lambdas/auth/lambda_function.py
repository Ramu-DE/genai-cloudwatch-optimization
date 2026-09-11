import json
import boto3
import os
import logging
import hashlib
import time
from datetime import datetime
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_REGION = os.environ.get('REGION', 'us-west-2')
AUTH_TABLE = os.environ.get('USER_AUTH_TABLE', 'wealth_mgmt_user_auth')
CLIENT_PROFILES_TABLE = os.environ.get('CLIENT_PROFILES_TABLE', 'wealth_mgmt_client_profiles')

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)


def hash_password(password, salt=None):
    """Hash password with SHA-256 and salt"""
    if not salt:
        salt = hashlib.sha256(os.urandom(32)).hexdigest()[:16]
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(stored_hash, password):
    """Verify password against stored hash"""
    salt = stored_hash.split(':')[0]
    return hash_password(password, salt) == stored_hash


def cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS, GET',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Api-Key',
        'Content-Type': 'application/json'
    }


def lambda_handler(event, context):
    logger.info(f"Auth Lambda invoked: {event.get('httpMethod', 'N/A')} {event.get('path', 'N/A')}")

    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': cors_headers(), 'body': ''}

    try:
        path = event.get('path', '')
        method = event.get('httpMethod', 'POST')

        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        if path.endswith('/login'):
            return handle_login(body)
        elif path.endswith('/register'):
            return handle_register(body)
        elif path.endswith('/profile'):
            return handle_get_profile(body, event)
        elif path.endswith('/validate'):
            return handle_validate_token(body, event)
        else:
            return {
                'statusCode': 404,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Endpoint not found'})
            }

    except Exception as e:
        logger.error(f"Auth error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Internal server error'})
        }


def handle_login(body):
    """Authenticate user and return session token"""
    email = body.get('email', '').strip().lower()
    password = body.get('password', '')

    if not email or not password:
        return {
            'statusCode': 400,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Email and password required'})
        }

    try:
        table = dynamodb.Table(AUTH_TABLE)
        response = table.get_item(Key={'email': email})

        if 'Item' not in response:
            return {
                'statusCode': 401,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Invalid credentials'})
            }

        user = response['Item']
        stored_hash = user.get('password_hash', '')

        if not verify_password(stored_hash, password):
            return {
                'statusCode': 401,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Invalid credentials'})
            }

        session_token = hashlib.sha256(
            f"{email}{time.time()}{os.urandom(16).hex()}".encode()
        ).hexdigest()

        table.update_item(
            Key={'email': email},
            UpdateExpression='SET last_login = :ts, session_token = :token',
            ExpressionAttributeValues={
                ':ts': datetime.now().isoformat(),
                ':token': session_token
            }
        )

        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({
                'token': session_token,
                'client_id': user.get('client_id', ''),
                'name': user.get('full_name', ''),
                'email': email,
                'role': user.get('role', 'client')
            })
        }

    except ClientError as e:
        logger.error(f"DynamoDB error: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Authentication service unavailable'})
        }


def handle_register(body):
    """Register a new client"""
    email = body.get('email', '').strip().lower()
    password = body.get('password', '')
    full_name = body.get('full_name', '')
    phone = body.get('phone', '')

    if not email or not password or not full_name:
        return {
            'statusCode': 400,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Email, password, and full name required'})
        }

    try:
        auth_table = dynamodb.Table(AUTH_TABLE)

        existing = auth_table.get_item(Key={'email': email})
        if 'Item' in existing:
            return {
                'statusCode': 409,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Email already registered'})
            }

        client_id = f"client_{full_name.lower().replace(' ', '_')}_{int(time.time()) % 10000}"
        password_hash = hash_password(password)

        auth_table.put_item(Item={
            'email': email,
            'client_id': client_id,
            'full_name': full_name,
            'phone': phone,
            'password_hash': password_hash,
            'role': 'client',
            'created_at': datetime.now().isoformat(),
            'status': 'active'
        })

        profiles_table = dynamodb.Table(CLIENT_PROFILES_TABLE)
        profiles_table.put_item(Item={
            'client_id': client_id,
            'full_name': full_name,
            'email': email,
            'phone': phone,
            'risk_tolerance': 'moderate',
            'investment_goals': ['general_growth'],
            'annual_income': 0,
            'net_worth': 0,
            'created_at': datetime.now().isoformat(),
            'kyc_status': 'PENDING',
            'status': 'active'
        })

        return {
            'statusCode': 201,
            'headers': cors_headers(),
            'body': json.dumps({
                'message': 'Registration successful',
                'client_id': client_id,
                'email': email
            })
        }

    except ClientError as e:
        logger.error(f"Registration error: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Registration failed'})
        }


def handle_get_profile(body, event):
    """Get client profile"""
    auth_header = event.get('headers', {}).get('Authorization', '')
    client_id = body.get('client_id', '')

    if not client_id:
        return {
            'statusCode': 400,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'client_id required'})
        }

    try:
        table = dynamodb.Table(CLIENT_PROFILES_TABLE)
        response = table.get_item(Key={'client_id': client_id})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Client not found'})
            }

        profile = response['Item']
        profile.pop('password_hash', None)

        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps(profile, default=str)
        }

    except ClientError as e:
        logger.error(f"Profile error: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Could not retrieve profile'})
        }


def handle_validate_token(body, event):
    """Validate session token"""
    token = body.get('token', '') or event.get('headers', {}).get('Authorization', '').replace('Bearer ', '')

    if not token:
        return {
            'statusCode': 401,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Token required'})
        }

    try:
        table = dynamodb.Table(AUTH_TABLE)
        response = table.query(
            IndexName='session_token-index',
            KeyConditionExpression='session_token = :token',
            ExpressionAttributeValues={':token': token},
            Limit=1
        )

        if not response.get('Items'):
            return {
                'statusCode': 401,
                'headers': cors_headers(),
                'body': json.dumps({'error': 'Invalid token'})
            }

        user = response['Items'][0]
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': json.dumps({
                'valid': True,
                'client_id': user.get('client_id'),
                'email': user.get('email'),
                'role': user.get('role', 'client')
            })
        }

    except ClientError as e:
        logger.error(f"Token validation error: {e}")
        return {
            'statusCode': 500,
            'headers': cors_headers(),
            'body': json.dumps({'error': 'Validation failed'})
        }
