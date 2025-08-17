import json
import os
import uuid
import time
import boto3
from botocore.exceptions import ClientError
from utils.password_utils import PasswordUtils


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
        
        # Debug the entire event
        print(f"DEBUG: Full event: {event}")
        print(f"DEBUG: Event body type: {type(event.get('body'))}")
        print(f"DEBUG: Event body: {event.get('body')}")
        
        print(f"DEBUG: Event processing started at: {start_time}")
        
        # Handle both direct event data and body-wrapped data
        if 'username' in event and 'email' in event and 'password' in event:
            # Direct event data (API Gateway passes JSON directly)
            body = event
            print("DEBUG: Using direct event data")
        else:
            # Traditional body-wrapped data
            body_raw = event.get('body', '{}')
            print(f"DEBUG: Using body-wrapped data: {body_raw}")
            
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
        
        # Extract and validate parameters
        username = body.get('username')
        email = body.get('email')
        password = body.get('password')
        
        # Debug logging
        print(f"DEBUG: Parsed body: {body}")
        print(f"DEBUG: username = '{username}' (type: {type(username)})")
        print(f"DEBUG: email = '{email}' (type: {type(email)})")
        print(f"DEBUG: password = '{password}' (type: {type(password)})")
        
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
        print(f"DEBUG: Checking username '{username}' and email '{email}' in table '{table_name}'")
        
        # Use GSI for efficient username/email lookups
        try:
            print(f"DEBUG: Attempting GSI scan on username-email-index")
            
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
            
            print(f"DEBUG: GSI scan result count: {gsi_response['Count']}")
            
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
            
            print("DEBUG: Username and email are available")
            
        except ClientError as e:
            # Fallback to scan if GSI scan fails
            print(f"DEBUG: GSI scan failed, falling back to table scan: {e}")
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
            
            print("DEBUG: Fallback scan completed - username and email are available")
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"DEBUG: DynamoDB ClientError - Code: {error_code}, Message: {error_message}")
            
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
        print(f"DEBUG: Password hashing took: {hash_end - hash_start:.3f} seconds")
        
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
            print(f"DEBUG: Saving user to table '{table_name}' with userId: {user_id}")
            print(f"DEBUG: User data: {user_data}")
            
            # Save with UUID as primary key
            table.put_item(
                Item=user_data,
                ConditionExpression='attribute_not_exists(userId)'  # Ensure UUID is unique
            )
            save_end = time.time()
            print(f"DEBUG: User saved successfully in: {save_end - save_start:.3f} seconds")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"DEBUG: DynamoDB PutItem ClientError - Code: {error_code}, Message: {error_message}")
            
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
        print(f"DEBUG: Total function execution time: {total_time:.3f} seconds")
        
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
                'message': f'An unexpected error occurred: {str(e)}'
            })
        } 