from base_handler import BaseLambdaHandler
from lambdas.utils.auth_middleware import require_auth
from lambdas.utils.db_utils import db_utils

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
connection_handler = ConnectionCountHandler()

# Lambda handler function
@require_auth()
def lambda_handler(event, context):
    return connection_handler.handle_request(event, context) 