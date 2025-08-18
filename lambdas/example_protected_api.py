import json
from utils.auth_middleware import require_auth, get_user_id_from_event, get_user_info_from_event


@require_auth()  # Uses default "Bridge/JWT" secret ID
def lambda_handler(event, context):
    """
    Example protected API endpoint that requires JWT authentication
    
    This demonstrates how to use the @require_auth decorator to protect
    your Lambda functions and access user information from the JWT token.
    
    For unauthenticated users, this will return a 401 error response.
    """
    try:
        # Get user information from the authenticated event
        user_id = get_user_id_from_event(event)
        user_info = get_user_info_from_event(event)
        
        # Your protected API logic here
        # For this example, we'll just return user information
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'message': 'Access granted to protected resource',
                'user_id': user_id,
                'user_info': user_info,
                'timestamp': '2024-01-01T00:00:00Z',
                'resource': 'example_protected_api'
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': f'An unexpected error occurred: {str(e)}'
            })
        }


@require_auth(redirect_on_failure=True, login_url="/login")
def lambda_handler_with_redirect(event, context):
    """
    Example protected API endpoint that redirects unauthenticated users to login
    
    This demonstrates how to use the @require_auth decorator with redirect functionality.
    For unauthenticated users, this will return a 302 redirect response to the login page.
    """
    try:
        # Get user information from the authenticated event
        user_id = get_user_id_from_event(event)
        user_info = get_user_info_from_event(event)
        
        # Your protected API logic here
        # For this example, we'll just return user information
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'message': 'Access granted to protected resource with redirect support',
                'user_id': user_id,
                'user_info': user_info,
                'timestamp': '2024-01-01T00:00:00Z',
                'resource': 'example_protected_api_with_redirect',
                'note': 'This endpoint redirects unauthenticated users to /login'
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': f'An unexpected error occurred: {str(e)}'
            })
        }


# Alternative way to use the decorator with custom secret ID or region
@require_auth(secret_id="Custom/JWT", region_name="us-west-2")
def lambda_handler_custom_secret(event, context):
    """
    Example using a custom secret ID and region
    
    This shows how to use different JWT secrets for different environments
    or services.
    """
    try:
        user_id = get_user_id_from_event(event)
        user_info = get_user_info_from_event(event)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'message': 'Access granted with custom secret configuration',
                'user_id': user_id,
                'user_info': user_info,
                'secret_id': 'Custom/JWT',
                'region': 'us-west-2'
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': f'An unexpected error occurred: {str(e)}'
            })
        }
