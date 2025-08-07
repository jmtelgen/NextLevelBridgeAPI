from base_handler import WebSocketBaseHandler
from db_utils import db_utils

class WebSocketConnectHandler(WebSocketBaseHandler):
    """
    WebSocket $connect handler
    Stores connection information in DynamoDB table
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket connect request
        """
        print(f"Processing WebSocket connect request: {event}")
        
        # Extract connection information
        connection_id = self.get_connection_id(event)
        request_time = event.get('requestContext', {}).get('requestTimeEpoch')
        user_info = self.get_user_info_from_query(event)
        
        print(f"Connection ID: {connection_id}")
        print(f"Request time: {request_time}")
        print(f"User info: {user_info}")
        
        if not connection_id:
            return self.error_response(400, 'Missing connection ID')
        
        # Create connection record using database utilities
        success = db_utils.create_connection_record(
            connection_id=connection_id,
            user_id=user_info.get('userId'),
            user_name=user_info.get('userName'),
            request_time=request_time
        )
        
        print(f"Connection record creation success: {success}")
        
        if not success:
            return self.error_response(500, 'Failed to create connection record')
        
        # For $connect, we don't need to return a response to the client
        # The connection is established automatically by API Gateway
        return {'statusCode': 200}

# Create handler instance
handler = WebSocketConnectHandler()

# Lambda handler function
def lambda_handler(event, context):
    print(f"LAMBDA HANDLER CALLED with event: {event}")
    print(f"Event type: {type(event)}")
    print(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'Not a dict'}")
    
    try:
        result = handler.handle_websocket_request(event, context)
        print(f"Handler result: {result}")
        return result
    except Exception as e:
        print(f"Exception in lambda_handler: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': f'Internal server error: {str(e)}'
        } 