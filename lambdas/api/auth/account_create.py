import json
import os
import sys
import uuid
import time
import boto3
from botocore.exceptions import ClientError

# Add the lambdas directory to the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lambdas.shared.security.password_utils import PasswordUtils


def lambda_handler(event, context):
    """
    Account creation API handler with bcrypt password hashing and salt
    
    Expected request body:
    {
        "username": "user@example.com",
        "email": "user@example.com",
        "password": "plaintext_password"
    }
    
    Returns:
    {
        "user": {
            "userId": "userId",
            "username": "username",
            "email": "email",
            "createdAt": "timestamp"
        },
        "message": "Account created successfully"
    }
    """
    try:
        import time
        start_time = time.time()
        
        
        # Handle both direct event data and body-wrapped data
        if 'username' in event and 'email' in event and 'password' in event:
            # Direct event data (API Gateway passes JSON directly)
            body = event
        else:
            # Traditional body-wrapped data
            body_raw = event.get('body', '{}')
            
            # Handle different body formats
            if isinstance(body_raw, str):
                if body_raw.strip() == '':
                    body_raw = '{}'
                try:
                    body = json.loads(body_raw)
                except json.JSONDecodeError as e:
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
                            'message': f'Request body must be valid JSON: {str(e)}'
                        })
                    }
            elif isinstance(body_raw, dict):
                body = body_raw
            else:
                body = {}
        
        if not isinstance(body, dict):
            return {'statusCode': 400, 'body': json.dumps({
                'error': 'Invalid request', 'message': 'Request body must be a JSON object'
            })}

        # Extract and validate parameters
        username = body.get('username')
        email = body.get('email')
        password = body.get('password')
        
        if any(value is not None and not isinstance(value, str)
               for value in (username, email, password)):
            return {'statusCode': 400, 'body': json.dumps({
                'error': 'Invalid request', 'message': 'Username, email and password must be strings'
            })}
        
        # Check for missing fields (handle empty strings)
        missing_fields = []
        if not username or (isinstance(username, str) and username.strip() == ''):
            missing_fields.append('username')
        if not email or (isinstance(email, str) and email.strip() == ''):
            missing_fields.append('email')
        if not password or (isinstance(password, str) and password.strip() == ''):
            missing_fields.append('password')
            
        if missing_fields:
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
                    'message': f'Missing required fields: {", ".join(missing_fields)}'
                })
            }
        
        # Validate password strength
        if len(username.strip()) < 3 or '@' not in email:
            return {'statusCode': 400, 'body': json.dumps({
                'error': 'Invalid account details',
                'message': 'Use a username of at least 3 characters and a valid email address'
            })}
        is_valid, error_message = PasswordUtils.validate_password_strength(password)
        if not is_valid:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Invalid password',
                    'message': error_message
                })
            }
        
        # Get DynamoDB table
        table_name = os.environ.get('USER_TABLE')
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        # Check if username or email already exists (optimized)
        
        # Use GSI for efficient username/email lookups
        try:
            
            # Try to query the GSI - we'll use scan on the index for now
            # since the exact key schema is unknown
            gsi_response = table.scan(
                IndexName='username-email-index',
                FilterExpression='username = :username OR email = :email',
                ExpressionAttributeValues={
                    ':username': username,
                    ':email': email
                },
                ProjectionExpression='username, email'
            )
            
            
            if gsi_response['Count'] > 0:
                for item in gsi_response['Items']:
                    if item.get('username') == username:
                        return {
                            'statusCode': 409,
                            'headers': {
                                'Content-Type': 'application/json',
                                'Access-Control-Allow-Origin': '*',
                                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                                'Access-Control-Allow-Methods': 'POST,OPTIONS'
                            },
                            'body': json.dumps({
                                'error': 'Username already exists',
                                'message': 'An account with this username already exists'
                            })
                        }
                    elif item.get('email') == email:
                        return {
                            'statusCode': 409,
                            'headers': {
                                'Content-Type': 'application/json',
                                'Access-Control-Allow-Origin': '*',
                                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                                'Access-Control-Allow-Methods': 'POST,OPTIONS'
                            },
                            'body': json.dumps({
                                'error': 'Email already exists',
                                'message': 'An account with this email already exists'
                            })
                        }
            
            
        except ClientError as e:
            # Fallback to scan if GSI scan fails
            try:
                response = table.scan(
                    FilterExpression='username = :username OR email = :email',
                    ExpressionAttributeValues={
                        ':username': username,
                        ':email': email
                    },
                    ProjectionExpression='username, email'
                )
                
                if response['Count'] > 0:
                    for item in response['Items']:
                        if item.get('username') == username:
                            return {
                                'statusCode': 409,
                                'headers': {
                                    'Content-Type': 'application/json',
                                    'Access-Control-Allow-Origin': '*',
                                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                                },
                                'body': json.dumps({
                                    'error': 'Username already exists',
                                    'message': 'An account with this username already exists'
                                })
                            }
                        elif item.get('email') == email:
                            return {
                                'statusCode': 409,
                                'headers': {
                                    'Content-Type': 'application/json',
                                    'Access-Control-Allow-Origin': '*',
                                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                                },
                                'body': json.dumps({
                                    'error': 'Email already exists',
                                    'message': 'An account with this email already exists'
                                })
                            }
                
                
            except ClientError as fallback_error:
                # If fallback scan also fails, handle the error
                error_code = fallback_error.response['Error']['Code']
                error_message = fallback_error.response['Error']['Message']
                
                if error_code == 'ResourceNotFoundException':
                    return {
                        'statusCode': 500,
                        'headers': {
                            'Content-Type': 'application/json',
                            'Access-Control-Allow-Origin': '*',
                            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                            'Access-Control-Allow-Methods': 'POST,OPTIONS'
                        },
                        'body': json.dumps({
                            'error': 'Table not found',
                            'message': f'DynamoDB table "{table_name}" does not exist'
                        })
                    }
                elif error_code == 'AccessDeniedException':
                    return {
                        'statusCode': 500,
                        'headers': {
                            'Content-Type': 'application/json',
                            'Access-Control-Allow-Origin': '*',
                            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                            'Access-Control-Allow-Methods': 'POST,OPTIONS'
                        },
                        'body': json.dumps({
                            'error': 'Access denied',
                            'message': f'Lambda does not have permission to access table "{table_name}"'
                        })
                    }
                else:
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
                            'message': f'DynamoDB error: {error_code} - {error_message}'
                        })
                    }
        
        # Generate user ID and timestamp
        user_id = str(uuid.uuid4())
        createdAt = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        
        # Hash password with enhanced salt for security
        hash_start = time.time()
        hashed_password, salt = PasswordUtils.hash_password(password)
        hash_end = time.time()
        
        # Create user object with UUID as primary key
        user_data = {
            'userId': user_id,  # UUID as primary key (camelCase for DynamoDB)
            'username': username,
            'email': email,
            'passwordHash': hashed_password,
            'salt': salt,
            'createdAt': createdAt  # camelCase for consistency
        }
        
        # Save user to database using UUID as primary key
        try:
            save_start = time.time()
            
            # Save with UUID as primary key
            table.put_item(
                Item=user_data,
                ConditionExpression='attribute_not_exists(userId)'  # Ensure UUID is unique
            )
            save_end = time.time()
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'ResourceNotFoundException':
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                        'Access-Control-Allow-Methods': 'POST,OPTIONS'
                    },
                    'body': json.dumps({
                        'error': 'Table not found',
                        'message': f'DynamoDB table "{table_name}" does not exist'
                    })
                }
            elif error_code == 'AccessDeniedException':
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                        'Access-Control-Allow-Methods': 'POST,OPTIONS'
                    },
                    'body': json.dumps({
                        'error': 'Access denied',
                        'message': f'Lambda does not have permission to access table "{table_name}"'
                    })
                }
            else:
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
                        'message': f'DynamoDB error: {error_code} - {error_message}'
                    })
                }
        
        # Create response (exclude sensitive data)
        response_user = {
            'userId': user_data['userId'],
            'username': user_data['username'],
            'email': user_data['email'],
            'createdAt': user_data['createdAt']
        }
        
        end_time = time.time()
        total_time = end_time - start_time
        
        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'message': 'Account created successfully',
                'user': response_user,
                'executionTime': f"{total_time:.3f}s"
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