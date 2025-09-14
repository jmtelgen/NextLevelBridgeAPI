import jwt
import json
import logging
from functools import wraps
from typing import Dict, Any, Optional, Callable
from .aws_secrets import get_jwt_secret

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def log_auth_event(event_type: str, details: Dict[str, Any]):
    """
    Log authentication events in a structured format for monitoring and analysis
    
    Args:
        event_type: Type of authentication event (attempt, success, failure, etc.)
        details: Dictionary containing event details
    """
    log_data = {
        'event_type': event_type,
        'timestamp': '2024-01-01T00:00:00Z',  # You can use datetime.now().isoformat() for real timestamp
        'details': details
    }
    
    if event_type in ['success', 'info']:
        logger.info(f"AUTH_EVENT: {json.dumps(log_data)}")
    elif event_type == 'warning':
        logger.warning(f"AUTH_EVENT: {json.dumps(log_data)}")
    elif event_type == 'error':
        logger.error(f"AUTH_EVENT: {json.dumps(log_data)}")
    else:
        logger.info(f"AUTH_EVENT: {json.dumps(log_data)}")


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
            # Log authentication attempt
            request_id = event.get('requestContext', {}).get('requestId', 'unknown')
            source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
            user_agent = event.get('headers', {}).get('User-Agent', 'unknown')
            http_method = event.get('httpMethod', 'unknown')
            path = event.get('path', 'unknown')
            
            # Log authentication attempt
            log_auth_event('attempt', {
                'request_id': request_id,
                'source_ip': source_ip,
                'user_agent': user_agent,
                'http_method': http_method,
                'path': path,
                'timestamp': '2024-01-01T00:00:00Z'
            })
            
            try:
                # Get user from the authenticated event
                user = get_user_from_event(event, secret_id, region_name)
                
                # Log successful authentication
                user_id = user.get('userId', 'unknown')
                username = user.get('username', 'unknown')
                log_auth_event('success', {
                    'request_id': request_id,
                    'user_id': user_id,
                    'username': username,
                    'source_ip': source_ip,
                    'http_method': http_method,
                    'path': path,
                    'timestamp': '2024-01-01T00:00:00Z'
                })
                
                # Add user to the event for the decorated function to use
                event['user'] = user
                
                # Call the original function
                return func(event, context)
                
            except Exception as e:
                # Log authentication failure
                error_message = str(e)
                error_type = "authentication_error"
                
                # Determine specific error type for better client handling
                if "Missing Authorization header" in error_message:
                    error_type = "missing_auth_header"
                elif "Invalid Authorization header format" in error_message:
                    error_type = "invalid_auth_format"
                elif "JWT token is missing" in error_message:
                    error_type = "missing_token"
                elif "expired" in error_message.lower():
                    error_type = "token_expired"
                elif "Invalid token type" in error_message:
                    error_type = "wrong_token_type"
                elif "Invalid JWT token" in error_message:
                    error_type = "invalid_token"
                elif "JWT secret key not found" in error_message:
                    error_type = "server_config_error"
                
                # Log the authentication failure with details
                log_auth_event('failure', {
                    'request_id': request_id,
                    'error_type': error_type,
                    'error_message': error_message,
                    'source_ip': source_ip,
                    'user_agent': user_agent,
                    'http_method': http_method,
                    'path': path,
                    'timestamp': '2024-01-01T00:00:00Z'
                })
                
                # Return standard error response with detailed information
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
                        'error_type': error_type,
                        'message': error_message,
                        'status_code': 401,
                        'timestamp': '2024-01-01T00:00:00Z'
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
        logger.warning("Missing Authorization header in request")
        raise Exception("Missing Authorization header. Please include 'Authorization: Bearer <token>' in your request headers.")
    
    # Extract token from "Bearer <token>" format
    if not auth_header.startswith('Bearer '):
        logger.warning(f"Invalid Authorization header format: {auth_header[:50]}...")
        raise Exception("Invalid Authorization header format. Must start with 'Bearer ' followed by your JWT token.")
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    
    if not token:
        logger.warning("Authorization header exists but contains no token")
        raise Exception("JWT token is missing. Please provide a valid JWT token after 'Bearer '.")
    
    logger.info(f"Token extracted successfully, length: {len(token)} characters")
    
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
        log_auth_event('info', {
            'action': 'token_validation_start',
            'secret_id': secret_id or 'default',
            'token_length': len(token)
        })
        
        # Get the JWT secret from AWS Secrets Manager
        secret_key = get_jwt_secret(secret_id, region_name)
        
        if not secret_key:
            log_auth_event('error', {
                'action': 'secret_key_not_found',
                'secret_id': secret_id or 'default'
            })
            raise Exception("JWT secret key not found. Please check your AWS Secrets Manager configuration.")
        
        log_auth_event('info', {
            'action': 'secret_key_retrieved',
            'secret_id': secret_id or 'default'
        })
        
        # Decode and verify the token
        payload = jwt.decode(token, secret_key, algorithms=['HS256'])
        log_auth_event('info', {
            'action': 'token_decoded',
            'payload_keys': list(payload.keys()),
            'token_type': payload.get('type'),
            'user_id': payload.get('userId')
        })
        
        # Check if it's an access token
        token_type = payload.get('type')
        if token_type != 'access':
            log_auth_event('warning', {
                'action': 'wrong_token_type',
                'expected_type': 'access',
                'actual_type': token_type
            })
            raise Exception("Invalid token type. This endpoint requires an access token, but you provided a refresh token.")
        
        # Check required fields
        user_id = payload.get('userId')
        if not user_id:
            log_auth_event('warning', {
                'action': 'missing_user_id',
                'payload_keys': list(payload.keys())
            })
            raise Exception("Token is missing required 'userId' field. Please log in again to get a valid token.")
        
        # Log token expiration info
        exp_timestamp = payload.get('exp')
        if exp_timestamp:
            from datetime import datetime
            exp_datetime = datetime.fromtimestamp(exp_timestamp)
            log_auth_event('info', {
                'action': 'token_expiration_info',
                'expires_at': exp_datetime.isoformat(),
                'user_id': user_id
            })
        
        # Return user information
        user_info = {
            'userId': user_id,
            'username': payload.get('username'),
            'email': payload.get('email')
        }
        
        log_auth_event('success', {
            'action': 'token_validation_complete',
            'user_id': user_id,
            'username': payload.get('username')
        })
        
        return user_info
        
    except jwt.ExpiredSignatureError:
        log_auth_event('warning', {
            'action': 'token_expired',
            'token_length': len(token)
        })
        raise Exception("Your access token has expired. Please refresh your token or log in again.")
    except jwt.InvalidTokenError as e:
        log_auth_event('warning', {
            'action': 'invalid_token',
            'error': str(e),
            'token_length': len(token)
        })
        raise Exception(f"Invalid JWT token: {str(e)}. Please check your token or log in again.")
    except Exception as e:
        log_auth_event('error', {
            'action': 'unexpected_validation_error',
            'error': str(e),
            'token_length': len(token)
        })
        raise Exception(f"Token validation failed: {str(e)}. Please try logging in again.")


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
