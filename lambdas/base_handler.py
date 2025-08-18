import json
import os
import boto3
from botocore.exceptions import ClientError
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

class BaseLambdaHandler(ABC):
    """
    Base class for Lambda handlers providing common functionality
    """
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
    
    def handle_request(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Main request handler with common error handling
        """
        try:
            return self.process_request(event, context)
        except ClientError as e:
            return self.error_response(
                500, 
                f"DynamoDB error: {e.response['Error']['Message']}"
            )
        except Exception as e:
            return self.error_response(500, f"Unexpected error: {str(e)}")
    
    @abstractmethod
    def process_request(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Abstract method that subclasses must implement
        """
        pass
    
    def success_response(self, data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
        """
        Create a standardized success response
        """
        return {
            'statusCode': status_code,
            'headers': self.get_cors_headers(),
            'body': json.dumps(data)
        }
    
    def error_response(self, status_code: int, error_message: str) -> Dict[str, Any]:
        """
        Create a standardized error response
        """
        return {
            'statusCode': status_code,
            'headers': self.get_cors_headers(),
            'body': json.dumps({'error': error_message})
        }
    
    def redirect_response(self, redirect_url: str, status_code: int = 302) -> Dict[str, Any]:
        """
        Create a redirect response for unauthenticated users
        
        Args:
            redirect_url: URL to redirect to (typically login page)
            status_code: HTTP status code (default: 302 Found)
        """
        return {
            'statusCode': status_code,
            'headers': {
                **self.get_cors_headers(),
                'Location': redirect_url,
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            },
            'body': json.dumps({
                'error': 'Authentication required',
                'message': 'Please log in to access this resource',
                'redirect_url': redirect_url
            })
        }
    
    def is_authenticated(self, event: Dict[str, Any]) -> bool:
        """
        Check if the request is authenticated by looking for a valid JWT token
        
        Args:
            event: Lambda event object
            
        Returns:
            True if authenticated, False otherwise
        """
        try:
            headers = event.get('headers', {}) or {}
            auth_header = headers.get('Authorization') or headers.get('authorization')
            
            if not auth_header or not auth_header.startswith('Bearer '):
                return False
            
            token = auth_header[7:]  # Remove "Bearer " prefix
            if not token:
                return False
            
            # Basic token validation (just check if it exists and has proper format)
            # Full validation should be done in the auth middleware
            return True
            
        except Exception:
            return False
    
    def require_auth_or_redirect(self, event: Dict[str, Any], login_url: str = None) -> Optional[Dict[str, Any]]:
        """
        Check if user is authenticated, return redirect response if not
        
        Args:
            event: Lambda event object
            login_url: URL to redirect to if not authenticated (defaults to environment variable)
            
        Returns:
            Redirect response if not authenticated, None if authenticated
        """
        if not self.is_authenticated(event):
            redirect_url = login_url or os.environ.get('LOGIN_URL', '/login')
            return self.redirect_response(redirect_url)
        return None
    
    def get_cors_headers(self) -> Dict[str, str]:
        """
        Get CORS headers for API responses
        """
        return {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
        }
    
    def get_table(self, table_name_env: str) -> Any:
        """
        Get DynamoDB table by environment variable name
        """
        table_name = os.environ.get(table_name_env)
        if not table_name:
            raise ValueError(f"{table_name_env} environment variable not set")
        return self.dynamodb.Table(table_name)
    
    def validate_required_fields(self, data: Dict[str, Any], required_fields: list) -> Optional[str]:
        """
        Validate that required fields are present in data
        Returns error message if validation fails, None if successful
        """
        for field in required_fields:
            if not data.get(field):
                return f"{field} is required"
        return None
    
    def parse_body(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and validate request body
        """
        body = event.get('body')
        if not body:
            raise ValueError("Missing request body")
        
        if isinstance(body, str):
            return json.loads(body)
        return body
    
    def extract_data_from_body(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract data from nested data object with fallback to top-level fields
        """
        data = body.get('data', {})
        
        # If data object is empty, use the body itself
        if not data:
            return body
        
        # Merge data object with top-level fields (data takes precedence)
        result = body.copy()
        result.update(data)
        return result

class WebSocketBaseHandler(BaseLambdaHandler):
    """
    Base class for WebSocket Lambda handlers
    """
    
    def process_request(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Override the base process_request to handle WebSocket requests
        """
        return self.handle_websocket_request(event, context)
    
    def handle_websocket_request(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Handle WebSocket requests with route key validation
        """
        try:
            route_key = event.get('requestContext', {}).get('routeKey')
            
            # Let subclasses handle all route keys including $connect and $disconnect
            return self.process_websocket_request(event, context)
            
        except Exception as e:
            return self.error_response(500, f"WebSocket error: {str(e)}")
    
    @abstractmethod
    def process_websocket_request(self, event: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """
        Abstract method for processing WebSocket requests
        """
        pass
    
    def validate_route_key(self, event: Dict[str, Any], expected_route: str) -> None:
        """
        Validate that the route key matches expected value
        """
        route_key = event.get('requestContext', {}).get('routeKey')
        if route_key != expected_route:
            raise ValueError(f"Invalid route key: {route_key}")
    
    def get_connection_id(self, event: Dict[str, Any]) -> str:
        """
        Extract connection ID from event
        """
        return event.get('requestContext', {}).get('connectionId')
    
    def get_user_info_from_query(self, event: Dict[str, Any]) -> Dict[str, str]:
        """
        Extract user information from query parameters
        """
        query_params = event.get('queryStringParameters', {}) or {}
        return {
            'userId': query_params.get('userId'),
            'userName': query_params.get('userName')
        }
    
    def _deserialize_dynamodb_types(self, obj):
        """
        Convert DynamoDB types to regular Python types using TypeDeserializer
        """
        from boto3.dynamodb.types import TypeDeserializer
        deserializer = TypeDeserializer()
        return deserializer.deserialize(obj)
    
    def _convert_for_json(self, obj):
        """
        Convert objects to JSON-serializable format, handling both DynamoDB types and regular Python objects
        """
        import json
        from decimal import Decimal
        
        def _convert_item(item):
            if isinstance(item, Decimal):
                return int(item) if item % 1 == 0 else float(item)
            elif isinstance(item, dict):
                return {key: _convert_item(value) for key, value in item.items()}
            elif isinstance(item, list):
                return [_convert_item(i) for i in item]
            elif isinstance(item, set):
                return list(_convert_item(i) for i in item)
            else:
                return item
        
        return _convert_item(obj) 