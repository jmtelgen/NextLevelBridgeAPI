import jwt
import json
from functools import wraps
from typing import Dict, Any, Optional, Callable
from .aws_secrets import get_jwt_secret


def require_auth(secret_id: str = None, region_name: Optional[str] = None):
    """
    Decorator to require JWT authentication for Lambda functions
    
    Args:
        secret_id: The AWS Secrets Manager secret ID for the JWT secret
                  If None, uses JWT_SECRET_ID environment variable or defaults to "Bridge/JWT"
        region_name: AWS region name. If None, uses default region from environment
        
    Usage:
        @require_auth()
        def lambda_handler(event, context):
            # Your protected Lambda function code here
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
            try:
                # Get user from the authenticated event
                user = get_user_from_event(event, secret_id, region_name)
                
                # Add user to the event for the decorated function to use
                event['user'] = user
                
                # Call the original function
                return func(event, context)
                
            except Exception as e:
                return {
                    'statusCode': 401,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
                    },
                    'body': json.dumps({
                        'error': 'Unauthorized',
                        'message': str(e)
                    })
                }
        return wrapper
    return decorator


def get_user_from_event(event: Dict[str, Any], secret_id: str = None, 
                       region_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract and validate user information from the Lambda event
    
    Args:
        event: Lambda event object
        secret_id: The AWS Secrets Manager secret ID for the JWT secret
                  If None, uses JWT_SECRET_ID environment variable or defaults to "Bridge/JWT"
        region_name: AWS region name. If None, uses default region from environment
        
    Returns:
        User information dictionary
        
    Raises:
        Exception: If authentication fails
    """
    # Check for Authorization header
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('Authorization') or headers.get('authorization')
    
    if not auth_header:
        raise Exception("Authorization header is required")
    
    # Extract token from "Bearer <token>" format
    if not auth_header.startswith('Bearer '):
        raise Exception("Authorization header must start with 'Bearer '")
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    if not token:
        raise Exception("JWT token is required")
    
    # Validate the token
    return validate_token(token, secret_id, region_name)


def validate_token(token: str, secret_id: str = None, 
                  region_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate a JWT token and return the user information
    
    Args:
        token: JWT token string
        secret_id: The AWS Secrets Manager secret ID for the JWT secret
                  If None, uses JWT_SECRET_ID environment variable or defaults to "Bridge/JWT"
        region_name: AWS region name. If None, uses default region from environment
        
    Returns:
        User information from the token payload
        
    Raises:
        Exception: If token validation fails
    """
    try:
        # Get the JWT secret from AWS Secrets Manager
        secret_key = get_jwt_secret(secret_id, region_name)
        
        if not secret_key:
            raise Exception("JWT secret key not found")
        
        # Decode and verify the token
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        
        # Check if it's an access token
        if payload.get('type') != 'access':
            raise Exception("Invalid token type. Access token required.")
        
        # Check required fields
        user_id = payload.get('userId')
        if not user_id:
            raise Exception("Token missing required userId field")
        
        # Return user information
        user_info = {
            'userId': user_id,
            'username': payload.get('username'),
            'email': payload.get('email')
        }
        
        return user_info
        
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError as e:
        raise Exception(f"Invalid token: {str(e)}")
    except Exception as e:
        raise Exception(f"Token validation failed: {str(e)}")


def get_user_id_from_event(event: Dict[str, Any]) -> str:
    """
    Extract user ID from the authenticated event
    
    Args:
        event: Lambda event object (must have been processed by @require_auth)
        
    Returns:
        User ID string
        
    Raises:
        Exception: If user information is not available
    """
    user = event.get('user')
    if not user:
        raise Exception("User information not available. Ensure @require_auth decorator is used.")
    
    user_id = user.get('userId')
    if not user_id:
        raise Exception("User ID not found in token")
    
    return user_id


def get_user_info_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract complete user information from the authenticated event
    
    Args:
        event: Lambda event object (must have been processed by @require_auth)
        
    Returns:
        User information dictionary
        
    Raises:
        Exception: If user information is not available
    """
    user = event.get('user')
    if not user:
        raise Exception("User information not available. Ensure @require_auth decorator is used.")
    
    return user
