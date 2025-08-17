import json
import os
from utils.jwt_utils import JWTUtils


def lambda_handler(event, context):
    """
    Lambda function to refresh JWT access tokens using valid refresh tokens
    """
    try:
        # Get refresh token from cookie
        cookies = event.get('headers', {}).get('Cookie', '') or event.get('headers', {}).get('cookie', '')
        refresh_token = None
        
        # Parse cookies to find refresh_token
        if cookies:
            for cookie in cookies.split(';'):
                if 'refresh_token=' in cookie:
                    refresh_token = cookie.split('refresh_token=')[1].strip()
                    break
        
        # Fallback to request body for backward compatibility
        if not refresh_token:
            # Handle both direct event data and body-wrapped data
            if 'refresh_token' in event:
                # Direct event data
                refresh_token = event.get('refresh_token')
            else:
                # Traditional body-wrapped data
                body_raw = event.get('body', '{}')
                if isinstance(body_raw, str):
                    body = json.loads(body_raw)
                elif isinstance(body_raw, dict):
                    body = body_raw
                else:
                    body = {}
                refresh_token = body.get('refresh_token')
        
        # Validate input
        if not refresh_token:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Missing required field',
                    'message': 'Refresh token is required (check cookies or request body)'
                })
            }
        
        # Initialize JWT utilities with AWS Secrets Manager
        try:
            jwt_utils = JWTUtils()  # Uses default "Bridge/JWT" secret ID
            print("DEBUG: JWT utilities initialized successfully")
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
        
        # Refresh the access token
        try:
            new_access_token = jwt_utils.refresh_access_token(refresh_token, expires_in_hours=24)
        except Exception as e:
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
                    'message': str(e)
                })
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
                'message': 'Token refreshed successfully',
                'accessToken': new_access_token,
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
