"""
Authentication utilities for Lambda functions

This module provides easy-to-use functions for protecting APIs with JWT authentication
and handling redirects for unauthenticated users.
"""

import json
import os
from typing import Dict, Any, Optional, Callable
from functools import wraps
from .jwt_utils import JWTUtils
from .aws_secrets import get_jwt_secret


def protect_api(secret_id: str = None, region_name: Optional[str] = None,
                redirect_on_failure: bool = False, login_url: str = None):
    """
    Decorator to protect API endpoints with JWT authentication
    
    Args:
        secret_id: The AWS Secrets Manager secret ID for the JWT secret
                  If None, uses JWT_SECRET_ID environment variable or defaults to "Bridge/JWT"
        region_name: AWS region name. If None, uses default region from environment
        redirect_on_failure: If True, return redirect response instead of error for unauthenticated users
        login_url: URL to redirect to if redirect_on_failure is True
        
    Usage:
        @protect_api()
        def lambda_handler(event, context):
            # Your protected Lambda function code here
            pass
            
        @protect_api(redirect_on_failure=True, login_url="/login")
        def protected_api(event, context):
            # Will redirect unauthenticated users to /login
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
            try:
                # Validate JWT token and extract user information
                user = validate_and_extract_user(event, secret_id, region_name)
                
                # Add user to the event for the decorated function to use
                event['user'] = user
                
                # Call the original function
                return func(event, context)
                
            except Exception as e:
                if redirect_on_failure:
                    # Return redirect response
                    redirect_url = login_url or os.environ.get('LOGIN_URL', '/login')
                    return create_redirect_response(redirect_url)
                else:
                    # Return standard error response
                    return create_unauthorized_response(str(e))
        return wrapper
    return decorator


def validate_and_extract_user(event: Dict[str, Any], secret_id: str = None, 
                            region_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Validate JWT token and extract user information from the Lambda event
    
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
    return validate_jwt_token(token, secret_id, region_name)


def validate_jwt_token(token: str, secret_id: str = None, 
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


def create_redirect_response(redirect_url: str, status_code: int = 302) -> Dict[str, Any]:
    """
    Create a redirect response for unauthenticated users
    
    Args:
        redirect_url: URL to redirect to (typically login page)
        status_code: HTTP status code (default: 302 Found)
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
            'Location': redirect_url,
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        },
        'body': json.dumps({
            'error': 'Authentication required',
            'message': 'Please log in to access this resource',
            'redirect_url': redirect_url
        })
    }


def create_unauthorized_response(error_message: str, status_code: int = 401) -> Dict[str, Any]:
    """
    Create an unauthorized response for unauthenticated users
    
    Args:
        error_message: Error message to include in response
        status_code: HTTP status code (default: 401 Unauthorized)
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps({
            'error': 'Unauthorized',
            'message': error_message
        })
    }


def get_user_id_from_event(event: Dict[str, Any]) -> str:
    """
    Extract user ID from the authenticated event
    
    Args:
        event: Lambda event object (must have been processed by @protect_api)
        
    Returns:
        User ID string
        
    Raises:
        Exception: If user information is not available
    """
    user = event.get('user')
    if not user:
        raise Exception("User information not available. Ensure @protect_api decorator is used.")
    
    user_id = user.get('userId')
    if not user_id:
        raise Exception("User ID not found in token")
    
    return user_id


def get_user_info_from_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract complete user information from the authenticated event
    
    Args:
        event: Lambda event object (must have been processed by @protect_api)
        
    Returns:
        User information dictionary
        
    Raises:
        Exception: If user information is not available
    """
    user = event.get('user')
    if not user:
        raise Exception("User information not available. Ensure @protect_api decorator is used.")
    
    return user


def is_authenticated(event: Dict[str, Any], secret_id: str = None, 
                    region_name: Optional[str] = None) -> bool:
    """
    Check if the request is authenticated by validating the JWT token
    
    Args:
        event: Lambda event object
        secret_id: The AWS Secrets Manager secret ID for the JWT secret
        region_name: AWS region name
        
    Returns:
        True if authenticated, False otherwise
    """
    try:
        validate_and_extract_user(event, secret_id, region_name)
        return True
    except Exception:
        return False


# Import jwt at the top level to avoid circular imports
import jwt
