import pytest
import json
import uuid
import os
from unittest.mock import patch, MagicMock
import sys

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.websocket_create_room import WebSocketCreateRoomHandler, lambda_handler


class TestWebSocketCreateRoomHandler:
    """Test cases for WebSocketCreateRoomHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create a WebSocketCreateRoomHandler instance for testing."""
        return WebSocketCreateRoomHandler()
    
    @pytest.fixture
    def sample_create_room_event(self):
        """Sample WebSocket create room event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'createRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'ownerId': 'test-user-123',
                'playerName': 'TestPlayer',
                'roomName': 'Test Room',
                'isPrivate': False
            })
        }
    
    @pytest.fixture
    def mock_context(self):
        """Mock Lambda context."""
        context = MagicMock()
        context.function_name = 'test-function'
        context.function_version = '1'
        context.memory_limit_in_mb = 128
        context.get_remaining_time_in_millis.return_value = 30000
        return context
    
    @pytest.fixture
    def mock_environment(self):
        """Set up test environment variables."""
        env_vars = {
            'ROOM_TABLE': 'test-rooms-table',
            'WEBSOCKET_CONNECTIONS_TABLE': 'test-connections-table'
        }
        
        # Store original values
        original_env = {}
        for key in env_vars:
            if key in os.environ:
                original_env[key] = os.environ[key]
        
        # Set test values
        for key, value in env_vars.items():
            os.environ[key] = value
        
        yield env_vars
        
        # Restore original values
        for key in env_vars:
            if key in original_env:
                os.environ[key] = original_env[key]
            else:
                del os.environ[key]
    
    def test_init(self, handler):
        """Test WebSocketCreateRoomHandler initialization."""
        assert handler is not None
    
    def test_process_websocket_request_success(self, handler, sample_create_room_event, mock_context, mock_environment):
        """Test successful room creation request processing."""
        with patch.object(handler, 'get_table') as mock_get_table, \
             patch.object(handler, '_update_user_room') as mock_update_user_room:
            
            mock_table = MagicMock()
            mock_get_table.return_value = mock_table
            mock_table.put_item.return_value = {}
            mock_update_user_room.return_value = True
            
            result = handler.process_websocket_request(sample_create_room_event, mock_context)
            
            assert result['statusCode'] == 201
            response_body = json.loads(result['body'])
            assert response_body['success'] is True
            assert response_body['action'] == 'createRoom'
            assert 'room' in response_body
            assert 'assignedSeat' in response_body
            assert 'gameState' in response_body
            assert response_body['message'] == 'Room created successfully'
            
            # Verify room was saved to DynamoDB
            mock_table.put_item.assert_called_once()
            saved_room = mock_table.put_item.call_args[1]['Item']
            assert saved_room['roomName'] == 'Test Room'
            assert saved_room['ownerId'] == 'test-user-123'
            assert saved_room['isPrivate'] is False
            assert saved_room['state'] == 'waiting'
            assert 'seats' in saved_room
            assert 'gameData' in saved_room
            
            # Verify user room was updated
            mock_update_user_room.assert_called_once()
    
    def test_process_websocket_request_missing_required_fields(self, handler, mock_context, mock_environment):
        """Test room creation with missing required fields."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'createRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'ownerId': 'test-user-123',
                # Missing playerName and roomName
                'isPrivate': False
            })
        }
        
        result = handler.process_websocket_request(event, mock_context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'error' in response_body
        assert 'Missing required field' in response_body['error']
    
    def test_process_websocket_request_empty_fields(self, handler, mock_context, mock_environment):
        """Test room creation with empty required fields."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'createRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'ownerId': '',
                'playerName': '',
                'roomName': '',
                'isPrivate': False
            })
        }
        
        result = handler.process_websocket_request(event, mock_context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'error' in response_body
        assert 'Missing required field' in response_body['error']
    
    def test_process_websocket_request_invalid_route_key(self, handler, mock_context, mock_environment):
        """Test room creation with invalid route key."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'invalidRoute',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'ownerId': 'test-user-123',
                'playerName': 'TestPlayer',
                'roomName': 'Test Room',
                'isPrivate': False
            })
        }
        
        result = handler.process_websocket_request(event, mock_context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'error' in response_body
        assert 'Invalid route key' in response_body['error']
    
    def test_process_websocket_request_dynamodb_error(self, handler, sample_create_room_event, mock_context, mock_environment):
        """Test room creation when DynamoDB operation fails."""
        with patch.object(handler, 'get_table') as mock_get_table:
            mock_table = MagicMock()
            mock_get_table.return_value = mock_table
            mock_table.put_item.side_effect = Exception("DynamoDB error")
            
            result = handler.process_websocket_request(sample_create_room_event, mock_context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'error' in response_body
            assert 'Unexpected error' in response_body['error']
    
    def test_process_websocket_request_update_user_room_failure(self, handler, sample_create_room_event, mock_context, mock_environment):
        """Test room creation when updating user room fails."""
        with patch.object(handler, 'get_table') as mock_get_table, \
             patch.object(handler, '_update_user_room') as mock_update_user_room:
            
            mock_table = MagicMock()
            mock_get_table.return_value = mock_table
            mock_table.put_item.return_value = {}
            mock_update_user_room.return_value = False
            
            result = handler.process_websocket_request(sample_create_room_event, mock_context)
            
            # Should still succeed since room was created
            assert result['statusCode'] == 201
            response_body = json.loads(result['body'])
            assert response_body['success'] is True
    
    def test_process_websocket_request_private_room(self, handler, mock_context, mock_environment):
        """Test private room creation."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'createRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'ownerId': 'test-user-123',
                'playerName': 'TestPlayer',
                'roomName': 'Private Test Room',
                'isPrivate': True
            })
        }
        
        with patch.object(handler, 'get_table') as mock_get_table, \
             patch.object(handler, '_update_user_room') as mock_update_user_room:
            
            mock_table = MagicMock()
            mock_get_table.return_value = mock_table
            mock_table.put_item.return_value = {}
            mock_update_user_room.return_value = True
            
            result = handler.process_websocket_request(event, mock_context)
            
            assert result['statusCode'] == 201
            response_body = json.loads(result['body'])
            assert response_body['success'] is True
            
            # Verify private room was created
            saved_room = mock_table.put_item.call_args[1]['Item']
            assert saved_room['isPrivate'] is True
    
    def test_log_request_info(self, handler, sample_create_room_event, mock_context):
        """Test request info logging."""
        request_id = handler._log_request_info(sample_create_room_event, mock_context)
        
        assert request_id is not None
        assert isinstance(request_id, str)
    
    def test_update_user_room(self, handler, mock_environment):
        """Test user room update functionality."""
        with patch('lambdas.websocket_create_room.db_utils') as mock_db_utils:
            mock_db_utils.update_user_room.return_value = True
            
            result = handler._update_user_room('test-user-123', 'test-room-123', 'test-request-id')
            
            assert result is True
            mock_db_utils.update_user_room.assert_called_once_with('test-user-123', 'test-room-123')


class TestWebSocketCreateRoomLambda:
    """Test cases for the lambda_handler function."""
    
    @pytest.fixture
    def sample_create_room_event(self):
        """Sample WebSocket create room event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'createRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'ownerId': 'test-user-123',
                'playerName': 'TestPlayer',
                'roomName': 'Test Room',
                'isPrivate': False
            })
        }
    
    def test_lambda_handler_success(self, sample_create_room_event):
        """Test successful lambda handler execution."""
        with patch('lambdas.websocket_create_room.handler') as mock_handler:
            mock_handler.handle_websocket_request.return_value = {'statusCode': 201}
            
            result = lambda_handler(sample_create_room_event, {})
            
            assert result['statusCode'] == 201
            mock_handler.handle_websocket_request.assert_called_once_with(sample_create_room_event, {})
    
    def test_lambda_handler_exception(self, sample_create_room_event):
        """Test lambda handler with exception."""
        with patch('lambdas.websocket_create_room.handler') as mock_handler:
            mock_handler.handle_websocket_request.side_effect = Exception("Test error")
            
            result = lambda_handler(sample_create_room_event, {})
            
            assert result['statusCode'] == 500
            assert 'Internal server error' in result['body']
    
    def test_lambda_handler_debug_logging(self, sample_create_room_event, caplog):
        """Test that lambda handler logs debug information."""
        with patch('lambdas.websocket_create_room.handler') as mock_handler:
            mock_handler.handle_websocket_request.return_value = {'statusCode': 201}
            
            lambda_handler(sample_create_room_event, {})
            
            assert 'LAMBDA HANDLER CALLED with event:' in caplog.text
            assert 'Event type:' in caplog.text
            assert 'Event keys:' in caplog.text
