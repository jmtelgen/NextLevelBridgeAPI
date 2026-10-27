import json
import boto3
import os
from botocore.exceptions import ClientError
from lambdas.shared.security.password_utils import PasswordUtils
from lambdas.shared.security.jwt_utils import JWTUtils


def find_login_user(table, username):
    """Filtered scan limits count scanned items, not matching accounts."""
    for use_index in (True, False):
        params = {
            'FilterExpression': 'username = :username OR email = :email',
            'ExpressionAttributeValues': {':username': username, ':email': username},
            'ProjectionExpression': 'userId, username, email, passwordHash, salt',
        }
        if use_index:
            params['IndexName'] = 'username-email-index'
        else:
            params['ConsistentRead'] = True
        try:
            while True:
                response = table.scan(**params)
                if response.get('Items'):
                    return response
                if not response.get('LastEvaluatedKey'):
                    if not use_index:
                        return response
                    break
                params['ExclusiveStartKey'] = response['LastEvaluatedKey']
        except ClientError:
            if not use_index:
                raise


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
        
        if not isinstance(body, dict):
            return {'statusCode': 400, 'body': json.dumps({
                'error': 'Invalid request', 'message': 'Request body must be a JSON object'
            })}
        username = body.get('username')
        password = body.get('password')
        
        # Validate input
        if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
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
            
            response = find_login_user(table, username)
            
            
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
                    'error': 'Database error',
                    'message': 'Failed to retrieve user information. Please try again.'
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
                    'message': 'Authentication is temporarily unavailable. Please try again.'
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
            access_token = jwt_utils.generate_access_token(user_data, expires_in_minutes=15)
            refresh_token = jwt_utils.generate_refresh_token(user_data, expires_in_days=7)
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
                    'message': 'Authentication is temporarily unavailable. Please try again.'
                })
            }
        
        # Prepare response (exclude sensitive information)
        response_user = {
            'userId': user_item.get('userId'),
            'username': user_item.get('username'),
            'email': user_item.get('email'),
            'createdAt': user_item.get('createdAt')
        }
        
        # Create the Set-Cookie header value
        set_cookie_value = f'refresh_token={refresh_token}; HttpOnly; Path=/; Max-Age=604800'
        
        # Add Secure flag only if using HTTPS (you can make this configurable)
        if os.environ.get('ENVIRONMENT') == 'production':
            set_cookie_value += '; Secure'
        
        # Add SameSite attribute
        set_cookie_value += '; SameSite=Strict'
        
        return {
            'statusCode': 200,
            'multiValueHeaders': {
                'Set-Cookie': [set_cookie_value]
            },
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': os.environ.get('FRONTEND_URL', '*'),
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'POST,OPTIONS',
                'Access-Control-Allow-Credentials': 'true'
            },
            'body': json.dumps({
                'message': 'Login successful',
                'accessToken': access_token,
                'user': response_user,
                'expiresIn': 900,  # 15 minutes in seconds
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
                'message': 'An unexpected error occurred. Please try again.'
            })
        } 