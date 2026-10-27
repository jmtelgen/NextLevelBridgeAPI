import json
import os
import logging
from lambdas.shared.security.jwt_utils import JWTUtils

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Lambda function to refresh JWT access tokens using valid refresh tokens
    
    This endpoint is UNPROTECTED and only validates the refresh token from cookies.
    It does NOT require an Authorization header with an access token.
    """
    try:
        # Log the refresh attempt
        request_id = event.get('requestContext', {}).get('requestId', 'unknown')
        source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
        
        logger.info(f"Token refresh attempt - RequestID: {request_id}, SourceIP: {source_ip}")
        
        # Get refresh token from cookie (primary method)
        cookies = event.get('headers', {}).get('Cookie', '') or event.get('headers', {}).get('cookie', '')
        refresh_token = None
        
        # Parse cookies to find refresh_token
        if cookies:
            for cookie in cookies.split(';'):
                cookie = cookie.strip()
                if cookie.startswith('refresh_token='):
                    refresh_token = cookie.split('refresh_token=', 1)[1]
                    break
        
        # Fallback to request body for backward compatibility
        if not refresh_token:
            logger.info("No refresh token in cookies, checking request body")
            # Handle both direct event data and body-wrapped data
            if 'refresh_token' in event:
                # Direct event data
                refresh_token = event.get('refresh_token')
            else:
                # Traditional body-wrapped data
                body_raw = event.get('body', '{}')
                if isinstance(body_raw, str):
                    try:
                        body = json.loads(body_raw)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in request body - RequestID: {request_id}")
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
                                'message': 'Request body must be valid JSON',
                                'request_id': request_id
                            })
                        }
                elif isinstance(body_raw, dict):
                    body = body_raw
                else:
                    body = {}
                refresh_token = body.get('refresh_token')
        
        # Validate input
        if not refresh_token:
            logger.warning(f"Refresh token not found - RequestID: {request_id}, SourceIP: {source_ip}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Missing refresh token',
                    'message': 'Refresh token not found in cookies or request body. Please log in again.',
                    'request_id': request_id
                })
            }
        
        # Initialize JWT utilities with AWS Secrets Manager
        try:
            jwt_utils = JWTUtils()  # Uses default "Bridge/JWT" secret ID
            logger.info(f"JWT utilities initialized successfully - RequestID: {request_id}")
        except Exception as e:
            logger.error("Failed to initialize JWT utilities")
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
                    'message': 'Authentication is temporarily unavailable. Please try again.',
                    'request_id': request_id
                })
            }
        
        # Refresh the access token
        try:
            logger.info(f"Attempting to refresh access token - RequestID: {request_id}")
            new_access_token = jwt_utils.refresh_access_token(refresh_token, expires_in_minutes=15)
            logger.info(f"Access token refreshed successfully - RequestID: {request_id}")
        except Exception as e:
            logger.warning("Token refresh rejected")
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Token refresh failed',
                    'message': 'Your session expired or is invalid. Please sign in again.',
                    'request_id': request_id
                })
            }
        
        # Success response
        logger.info(f"Token refresh completed successfully - RequestID: {request_id}")
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': os.environ.get('FRONTEND_URL', '*'),
                'Access-Control-Allow-Credentials': 'true',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'POST,OPTIONS',
                'Cache-Control': 'no-store'
            },
            'body': json.dumps({
                'message': 'Token refreshed successfully',
                'accessToken': new_access_token,
                'expiresIn': 900,  # 15 minutes in seconds
                'tokenType': 'Bearer',
                'request_id': request_id
            })
        }
        
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON during token refresh")
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
                'message': 'Request body must be valid JSON',
                'request_id': request_id
            })
        }
    except Exception as e:
        logger.error("Unexpected token refresh failure")
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
                'message': 'An unexpected error occurred. Please sign in again.',
                'request_id': request_id
            })
        }
