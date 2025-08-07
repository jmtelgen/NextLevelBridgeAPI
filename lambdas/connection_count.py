from base_handler import BaseLambdaHandler
from db_utils import db_utils

class ConnectionCountHandler(BaseLambdaHandler):
    """
    REST API handler for getting the count of active WebSocket connections
    """
    
    def process_request(self, event, context):
        """
        Process the connection count request
        """
        # Check if this is a GET request
        if event.get('httpMethod') != 'GET':
            return self.error_response(405, 'Method not allowed')
        
        # Get both active user count and active room count using database utilities
        stats = db_utils.get_connection_stats()
        
        return self.success_response(stats)

# Create handler instance
handler = ConnectionCountHandler()

# Lambda handler function
def handler(event, context):
    return handler.handle_request(event, context) 