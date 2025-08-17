import json
import boto3
import os
from botocore.exceptions import ClientError
from utils.password_utils import PasswordUtils
from utils.jwt_utils import JWTUtils


def lambda_handler(event, context):
    """
    Lambda function to handle user login and JWT token generation
    """
    try:
        # Handle both direct event data and body-wrapped data
        if 'username' in event and 'password' in event:
            # Direct event data (API Gateway passes JSON directly)
            body = event
        else:
            # Traditional body-wrapped data
            body_raw = event.get('body', '{}')
            if isinstance(body_raw, str):
                body = json.loads(body_raw)
            elif isinstance(body_raw, dict):
                body = body_raw
            else:
                body = {}
        
        username = body.get('username')
        password = body.get('password')
        
        # Validate input
        if not username or not password:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Missing required fields',
                    'message': 'Username and password are required'
                })
            }
        
        # Initialize DynamoDB client
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('USER_TABLE', 'Users')
        table = dynamodb.Table(table_name)
        
        # Look up user by username or email
        try:
            print(f"DEBUG: Looking up user by username/email: {username}")
            
            # Try to find user by username or email using GSI
            response = None
            try:
                print(f"DEBUG: Attempting GSI scan on username-email-index")
                
                # Use GSI scan since the exact key schema is unknown
                response = table.scan(
                    IndexName='username-email-index',
                    FilterExpression='username = :username OR email = :email',
                    ExpressionAttributeValues={
                        ':username': username,
                        ':email': username
                    },
                    ProjectionExpression='userId, username, email, passwordHash, salt',
                    Limit=1
                )
                
                print(f"DEBUG: GSI scan result count: {response['Count']}")
                
            except ClientError as e:
                # Fallback to table scan if GSI scan fails
                print(f"DEBUG: GSI scan failed, falling back to table scan: {e}")
                response = table.scan(
                    FilterExpression='username = :username OR email = :email',
                    ExpressionAttributeValues={
                        ':username': username,
                        ':email': username
                    },
                    ProjectionExpression='userId, username, email, passwordHash, salt',
                    Limit=1
                )
            
            print(f"DEBUG: Scan result count: {response['Count']}")
            
            if response['Count'] == 0:
                return {
                    'statusCode': 401,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                        'Access-Control-Allow-Methods': 'POST,OPTIONS'
                    },
                    'body': json.dumps({
                        'error': 'Authentication failed',
                        'message': 'Invalid username/email or password'
                    })
                }
            
            # Get the first matching user
            user_item = response['Items'][0]
            print(f"DEBUG: Found user: {user_item.get('userId')}")
            
        except Exception as e:
            print(f"DEBUG: Exception during user lookup: {str(e)}")
            
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Database error',
                    'message': f'Failed to retrieve user information: {str(e)}'
                })
            }
        
        # Verify password
        stored_password_hash = user_item.get('passwordHash')
        stored_salt = user_item.get('salt')
        
        if not stored_password_hash or not stored_salt:
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Authentication failed',
                    'message': 'Invalid username or password'
                })
            }
        
        # Verify password using bcrypt
        if not PasswordUtils.verify_password(password, stored_password_hash, stored_salt):
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Authentication failed',
                    'message': 'Invalid username or password'
                })
            }
        
        # Initialize JWT utilities with AWS Secrets Manager
        try:
            jwt_utils = JWTUtils()  # Uses default "Bridge/JWT" secret ID
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Configuration error',
                    'message': f'Failed to initialize JWT utilities: {str(e)}'
                })
            }
        
        # Prepare user data for token generation
        user_data = {
            'userId': user_item.get('userId'),
            'username': user_item.get('username'),
            'email': user_item.get('email')
        }
        
        # Generate JWT tokens
        try:
            access_token = jwt_utils.generate_access_token(user_data, expires_in_hours=24)
            refresh_token = jwt_utils.generate_refresh_token(user_data, expires_in_days=30)
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Token generation failed',
                    'message': f'Failed to generate authentication tokens: {str(e)}'
                })
            }
        
        # Prepare response (exclude sensitive information)
        response_user = {
            'userId': user_item.get('userId'),
            'username': user_item.get('username'),
            'email': user_item.get('email'),
            'createdAt': user_item.get('createdAt')
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'POST,OPTIONS',
                'Set-Cookie': f'refresh_token={refresh_token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=2592000'  # 30 days
            },
            'body': json.dumps({
                'message': 'Login successful',
                'accessToken': access_token,
                'user': response_user,
                'expiresIn': 86400,  # 24 hours in seconds
                'tokenType': 'Bearer'
            })
        }
        
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Invalid JSON',
                'message': 'Request body must be valid JSON'
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': f'An unexpected error occurred: {str(e)}'
            })
        } 