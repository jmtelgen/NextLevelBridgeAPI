# Lambda Function Refactoring Guide

This document outlines the refactored architecture for the BridgeLambdas project, which introduces base classes and utility functions to reduce code duplication and improve maintainability.

## Architecture Overview

### Base Classes

#### `BaseLambdaHandler`
- **Location**: `lambdas/base_handler.py`
- **Purpose**: Base class for all Lambda handlers providing common functionality
- **Features**:
  - Standardized error handling
  - CORS headers
  - Response formatting
  - DynamoDB table access
  - Request body parsing
  - Field validation

#### `WebSocketBaseHandler`
- **Location**: `lambdas/base_handler.py`
- **Purpose**: Base class specifically for WebSocket Lambda handlers
- **Features**:
  - WebSocket route key validation
  - Connection ID extraction
  - User info extraction from query parameters
  - Standard WebSocket event handling ($connect, $disconnect)

### Utility Classes

#### `DatabaseUtils`
- **Location**: `lambdas/db_utils.py`
- **Purpose**: Centralized database operations
- **Features**:
  - Connection record management
  - Room operations
  - Active room counting
  - User room updates

#### `WebSocketUtils`
- **Location**: `lambdas/websocket_utils.py`
- **Purpose**: WebSocket-specific utilities
- **Features**:
  - Message sending
  - Broadcasting
  - Connection management

## Usage Examples

### Creating a REST API Handler

```python
from base_handler import BaseLambdaHandler
from db_utils import db_utils

class MyRestHandler(BaseLambdaHandler):
    def process_request(self, event, context):
        # Validate HTTP method
        if event.get('httpMethod') != 'GET':
            return self.error_response(405, 'Method not allowed')
        
        # Parse and validate request body
        body = self.parse_body(event)
        error = self.validate_required_fields(body, ['userId', 'roomId'])
        if error:
            return self.error_response(400, error)
        
        # Use database utilities
        room = db_utils.find_room_by_id(body['roomId'])
        if not room:
            return self.error_response(404, 'Room not found')
        
        # Return success response
        return self.success_response({'room': room})

# Create handler instance
handler = MyRestHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_request(event, context)
```

### Creating a WebSocket Handler

```python
from base_handler import WebSocketBaseHandler
from db_utils import db_utils
from websocket_utils import broadcast_to_connections

class MyWebSocketHandler(WebSocketBaseHandler):
    def process_websocket_request(self, event, context):
        # Validate route key
        self.validate_route_key(event, 'myAction')
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Validate required fields
        error = self.validate_required_fields(data, ['userId'])
        if error:
            return self.error_response(400, error)
        
        # Use database utilities
        success = db_utils.update_user_room(data['userId'], data['roomId'])
        if not success:
            return self.error_response(500, 'Failed to update user room')
        
        # Return success response
        return self.success_response({'success': True})

# Create handler instance
handler = MyWebSocketHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context)
```

## Benefits of Refactoring

### 1. **Reduced Code Duplication**
- Common error handling logic is centralized
- Database operations are standardized
- Response formatting is consistent

### 2. **Improved Maintainability**
- Changes to error handling only need to be made in one place
- Database schema changes are handled in utility classes
- New features can be added to base classes

### 3. **Better Error Handling**
- Consistent error responses across all APIs
- Proper CORS headers
- Standardized error messages

### 4. **Type Safety**
- Added type hints for better IDE support
- Clearer function signatures
- Better documentation

### 5. **Easier Testing**
- Base classes can be mocked easily
- Utility functions can be tested independently
- Consistent test patterns

## Migration Guide

### Step 1: Update Imports
Replace direct DynamoDB operations with utility calls:

```python
# Before
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME'))

# After
from db_utils import db_utils
table = db_utils.get_table('TABLE_NAME')
```

### Step 2: Use Base Classes
Replace manual error handling with base class methods:

```python
# Before
try:
    # ... logic ...
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(result)
    }
except Exception as e:
    return {
        'statusCode': 500,
        'body': json.dumps({'error': str(e)})
    }

# After
from base_handler import BaseLambdaHandler

class MyHandler(BaseLambdaHandler):
    def process_request(self, event, context):
        # ... logic ...
        return self.success_response(result)
```

### Step 3: Update Response Format
Use standardized response methods:

```python
# Before
return {'statusCode': 400, 'body': json.dumps({'error': 'Bad request'})}

# After
return self.error_response(400, 'Bad request')
```

## Refactored Files

### New Files
- `lambdas/base_handler.py` - Base classes for Lambda handlers
- `lambdas/db_utils.py` - Database utility functions
- `lambdas/connection_count_refactored.py` - Example refactored REST API
- `lambdas/websocket_connect_refactored.py` - Example refactored WebSocket handler
- `lambdas/websocket_join_room_refactored.py` - Example refactored WebSocket handler

### Enhanced Files
- `lambdas/websocket_utils.py` - Added type hints and improved documentation

## Testing

The refactored code maintains the same functionality while providing better structure. All existing tests should continue to pass, and new tests can be written more easily using the base classes.

## Future Enhancements

1. **Middleware Support**: Add middleware for logging, authentication, etc.
2. **Validation Schemas**: Add JSON schema validation for request bodies
3. **Rate Limiting**: Add rate limiting utilities
4. **Caching**: Add caching utilities for frequently accessed data
5. **Metrics**: Add built-in metrics collection

## Conclusion

The refactored architecture provides a solid foundation for building maintainable, scalable Lambda functions while reducing code duplication and improving error handling consistency. 