
import json
import boto3
import os
from decimal import Decimal

def decimal_to_native(obj):
    """Convert DynamoDB Decimal types to native Python types"""
    try:
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        elif isinstance(obj, dict):
            return {k: decimal_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [decimal_to_native(v) for v in obj]
        return obj
    except Exception as e:
        print(f"Error in decimal_to_native: {str(e)}")
        return obj

def get_user_appointments(username, customer_id, appointments_table):
    """Get appointments for a user"""
    try:
        appointments = []
        
        # Search by customerId
        response = appointments_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('customerId').eq(customer_id)
        )
        appointments.extend(response['Items'])
        
        # Search by customer_id (with underscore) if different
        try:
            response = appointments_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('customer_id').eq(customer_id)
            )
            appointments.extend(response['Items'])
        except:
            pass
        
        # Search by username if different results
        if customer_id != username:
            response = appointments_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(username)
            )
            appointments.extend(response['Items'])
        
        # Remove duplicates
        seen_ids = set()
        unique_appointments = []
        for apt in appointments:
            apt_id = apt.get('appointmentId', str(apt))
            if apt_id not in seen_ids:
                seen_ids.add(apt_id)
                unique_appointments.append(apt)
        
        print(f"Found {len(unique_appointments)} appointments for {username}")
        return unique_appointments
    
    except Exception as e:
        print(f"Error getting appointments: {str(e)}")
        return []

def lambda_handler(event, context):
    try:
        print(f"Event received: {json.dumps(event, default=str)}")
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type, Authorization'
                },
                'body': ''
            }
        
        # Parse request body
        body = None
        try:
            if 'body' in event and event['body']:
                if isinstance(event['body'], str):
                    body = json.loads(event['body'])
                else:
                    body = event['body']
            else:
                body = event
        except Exception as e:
            print(f"Error parsing body: {str(e)}")
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Invalid request body'})
            }
        
        username = body.get('username') if body else None
        password = body.get('password') if body else None
        
        if not username or not password:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Username and password required'})
            }
        
        print(f"Authenticating user: {username}")
        
        # Connect to DynamoDB (AWS_REGION is automatically set by Lambda)
        try:
            region = os.environ.get('AWS_REGION', 'us-west-2')
            dynamodb = boto3.resource('dynamodb', region_name=region)
            # Use USER_AUTH_TABLE for authentication (not customer_profiles)
            user_auth_table = dynamodb.Table(os.environ.get('USER_AUTH_TABLE', os.environ.get('CUSTOMER_PROFILES_TABLE', '')))
            appointments_table = dynamodb.Table(os.environ['APPOINTMENTS_TABLE'])
        except Exception as e:
            print(f"DynamoDB connection error: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Database connection error'})
            }
        
        # Search for user in user_auth table
        try:
            response = user_auth_table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(username)
            )
            items = response['Items']
        except Exception as e:
            print(f"Database query error: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Database query error'})
            }
        
        if not items:
            return {
                'statusCode': 401,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Invalid credentials'})
            }
        
        user = items[0]
        stored_password = user.get('password')
        
        if stored_password != password:
            return {
                'statusCode': 401,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Invalid credentials'})
            }
        
        # Process user data
        try:
            user_data = decimal_to_native(dict(user))
            
            # Remove password
            if 'password' in user_data:
                del user_data['password']
            
            # Get customer_id - Check customer_id first, then customerId
            customer_id = user_data.get('customer_id') or user_data.get('customerId') or username
            print(f"Using customer_id: {customer_id} for user: {username}")
            
            # Get appointments
            appointments = get_user_appointments(username, customer_id, appointments_table)
            appointments_data = decimal_to_native(appointments)
            
            # Get pets data
            pets = user_data.get('pets', [])
            pets_count = len(pets) if pets else 0
            
            # Build response with appointments
            response_data = {
                'success': True,
                'username': user_data.get('username', username),
                'name': user_data.get('name', 'Unknown'),
                'full_name': user_data.get('full_name', user_data.get('name', 'Unknown')),
                'email': user_data.get('email', ''),
                'customerId': customer_id,
                'customer_id': customer_id,
                'pets': pets,
                'pets_count': pets_count,
                'appointments': appointments_data,
                'appointments_count': len(appointments_data),
                'has_pets': pets_count > 0,
                'membership_level': user_data.get('membership_level', 'Basic'),
                'phone': user_data.get('phone', ''),
                'address': user_data.get('address', {}),
                'message': 'Authentication successful'
            }
            
            print(f"Returning response with {pets_count} pets and {len(appointments_data)} appointments")
            print(f"Customer ID in response: {customer_id}")
            
            return {
                'statusCode': 200,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps(response_data)
            }
        
        except Exception as e:
            print(f"Error processing user data: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
                'body': json.dumps({'success': False, 'message': 'Error processing user data'})
            }
    
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'},
            'body': json.dumps({'success': False, 'message': 'Internal server error'})
        }
