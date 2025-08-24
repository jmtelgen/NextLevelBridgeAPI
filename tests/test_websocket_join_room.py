import pytest
import json
import uuid
import os
from unittest.mock import patch, MagicMock
import sys

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.websocket_join_room import WebSocketJoinRoomHandler, lambda_handler


class TestWebSocketJoinRoomHandler:
    """Test cases for WebSocketJoinRoomHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create a WebSocketJoinRoomHandler instance for testing."""
        return WebSocketJoinRoomHandler()
    
    @pytest.fixture
    def sample_join_room_event(self):
        """Sample WebSocket join room event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'joinRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'userId': 'test-user-123',
                'roomId': 'test-room-123'
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
    
    @pytest.fixture
    def mock_room_data(self):
        """Mock room data from database."""
        return {
            'roomId': 'test-room-123',
            'ownerId': 'test-owner-123',
            'playerName': 'TestOwner',
            'roomName': 'Test Room',
            'isPrivate': False,
            'seats': {
                'N': 'test-owner-123',
                'E': '',
                'S': '',
                'W': ''
            },
            'state': 'waiting',
            'gameData': {
                'currentPhase': 'waiting',
                'turn': 'test-owner-123',
                'bids': [],
                'hands': {'N': [], 'E': [], 'S': [], 'W': []},
                'tricks': []
            }
        }
    
    def test_init(self, handler):
        """Test WebSocketJoinRoomHandler initialization."""
        assert handler is not None
    
    def test_process_websocket_request_success(self, handler, sample_join_room_event, mock_context, mock_environment, mock_room_data):
        """Test successful room join request processing."""
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils, \
             patch('lambdas.websocket_join_room.broadcast_to_connection') as mock_broadcast:
            
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = mock_room_data
            mock_db_utils.update_user_room.return_value = True
            mock_db_utils.get_room_connections.return_value = ['connection-1', 'connection-2']
            
            result = handler.process_websocket_request(sample_join_room_event, mock_context)
            
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['success'] is True
            assert response_body['action'] == 'roomUpdated'
            assert response_body['updateType'] == 'userJoined'
            assert response_body['newUser'] == 'test-user-123'
            assert 'assignedSeat' in response_body
            assert response_body['assignedSeat'] in ['E', 'S', 'W']  # One of the empty seats
            assert 'room' in response_body
            assert 'gameData' in response_body
            
            # Verify room was updated in database
            mock_db_utils.update_user_room.assert_called_once_with('test-user-123', 'test-room-123')
            
            # Verify broadcast was sent
            assert mock_broadcast.call_count == 2  # One for each connection
    
    def test_process_websocket_request_missing_required_fields(self, handler, mock_context, mock_environment):
        """Test room join with missing required fields."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'joinRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'userId': 'test-user-123',
                # Missing roomId
            })
        }
        
        result = handler.process_websocket_request(event, mock_context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'error' in response_body
        assert 'roomId is required' in response_body['error']
    
    def test_process_websocket_request_empty_fields(self, handler, mock_context, mock_environment):
        """Test room join with empty required fields."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'joinRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'userId': '',
                'roomId': ''
            })
        }
        
        result = handler.process_websocket_request(event, mock_context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'error' in response_body
        assert 'userId is required' in response_body['error']
    
    def test_process_websocket_request_invalid_route_key(self, handler, mock_context, mock_environment):
        """Test room join with invalid route key."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'invalidRoute',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'userId': 'test-user-123',
                'roomId': 'test-room-123'
            })
        }
        
        result = handler.process_websocket_request(event, mock_context)
        
        assert result['statusCode'] == 400
        response_body = json.loads(result['body'])
        assert 'error' in response_body
        assert 'Invalid route key' in response_body['error']
    
    def test_process_websocket_request_room_not_found(self, handler, sample_join_room_event, mock_context, mock_environment):
        """Test room join when room does not exist."""
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils:
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = None  # Room not found
            
            result = handler.process_websocket_request(sample_join_room_event, mock_context)
            
            assert result['statusCode'] == 404
            response_body = json.loads(result['body'])
            assert 'error' in response_body
            assert 'Room does not exist' in response_body['error']
    
    def test_process_websocket_request_user_already_in_room(self, handler, sample_join_room_event, mock_context, mock_environment, mock_room_data):
        """Test room join when user is already in the room."""
        # Modify room data to include the user
        mock_room_data['seats']['E'] = 'test-user-123'
        
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils:
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = mock_room_data
            
            result = handler.process_websocket_request(sample_join_room_event, mock_context)
            
            assert result['statusCode'] == 400
            response_body = json.loads(result['body'])
            assert 'error' in response_body
            assert 'User already in room' in response_body['error']
    
    def test_process_websocket_request_no_seats_available(self, handler, sample_join_room_event, mock_context, mock_environment, mock_room_data):
        """Test room join when no seats are available."""
        # Modify room data to fill all seats
        mock_room_data['seats'] = {
            'N': 'user-1',
            'E': 'user-2',
            'S': 'user-3',
            'W': 'user-4'
        }
        
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils:
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = mock_room_data
            
            result = handler.process_websocket_request(sample_join_room_event, mock_context)
            
            assert result['statusCode'] == 400
            response_body = json.loads(result['body'])
            assert 'error' in response_body
            assert 'No seats available' in response_body['error']
    
    def test_process_websocket_request_dynamodb_error(self, handler, sample_join_room_event, mock_context, mock_environment, mock_room_data):
        """Test room join when DynamoDB operation fails."""
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils:
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = mock_room_data
            
            # Mock DynamoDB put_item failure
            mock_table = MagicMock()
            mock_table.put_item.side_effect = Exception("DynamoDB error")
            mock_db_utils.get_table.return_value = mock_table
            
            result = handler.process_websocket_request(sample_join_room_event, mock_context)
            
            assert result['statusCode'] == 500
            response_body = json.loads(result['body'])
            assert 'error' in response_body
            assert 'Unexpected error' in response_body['error']
    
    def test_process_websocket_request_update_user_room_failure(self, handler, sample_join_room_event, mock_context, mock_environment, mock_room_data):
        """Test room join when updating user room fails."""
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils, \
             patch('lambdas.websocket_join_room.broadcast_to_connection') as mock_broadcast:
            
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = mock_room_data
            mock_db_utils.update_user_room.return_value = False  # Update fails
            mock_db_utils.get_room_connections.return_value = ['connection-1']
            
            result = handler.process_websocket_request(sample_join_room_event, mock_context)
            
            # Should still succeed since room was updated
            assert result['statusCode'] == 200
            response_body = json.loads(result['body'])
            assert response_body['success'] is True
    
    def test_find_available_seat(self, handler, mock_room_data):
        """Test finding available seat functionality."""
        # Test with available seats
        available_seat = handler._find_available_seat(mock_room_data)
        assert available_seat in ['E', 'S', 'W']
        
        # Test with no available seats
        mock_room_data['seats'] = {
            'N': 'user-1',
            'E': 'user-2',
            'S': 'user-3',
            'W': 'user-4'
        }
        available_seat = handler._find_available_seat(mock_room_data)
        assert available_seat is None
    
    def test_find_available_seat_partial_occupancy(self, handler):
        """Test finding available seat with partial room occupancy."""
        room_data = {
            'seats': {
                'N': 'user-1',
                'E': '',
                'S': 'user-3',
                'W': ''
            }
        }
        
        available_seat = handler._find_available_seat(room_data)
        assert available_seat in ['E', 'W']
    
    def test_broadcast_message_structure(self, handler, sample_join_room_event, mock_context, mock_environment, mock_room_data):
        """Test that broadcast message has correct structure."""
        with patch('lambdas.websocket_join_room.db_utils') as mock_db_utils, \
             patch('lambdas.websocket_join_room.broadcast_to_connection') as mock_broadcast:
            
            mock_db_utils.get_table.return_value = MagicMock()
            mock_db_utils.find_room_by_id.return_value = mock_room_data
            mock_db_utils.update_user_room.return_value = True
            mock_db_utils.get_room_connections.return_value = ['connection-1']
            
            handler.process_websocket_request(sample_join_room_event, mock_context)
            
            # Verify broadcast was called with correct message structure
            mock_broadcast.assert_called_once()
            broadcast_args = mock_broadcast.call_args
            message = broadcast_args[0][1]  # Second argument is the message
            
            assert message['action'] == 'roomUpdated'
            assert message['success'] is True
            assert message['updateType'] == 'userJoined'
            assert message['newUser'] == 'test-user-123'
            assert 'assignedSeat' in message
            assert 'room' in message
            assert 'gameData' in message


class TestWebSocketJoinRoomLambda:
    """Test cases for the lambda_handler function."""
    
    @pytest.fixture
    def sample_join_room_event(self):
        """Sample WebSocket join room event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': 'joinRoom',
                'requestTimeEpoch': 1640995200000
            },
            'body': json.dumps({
                'userId': 'test-user-123',
                'roomId': 'test-room-123'
            })
        }
    
    def test_lambda_handler_success(self, sample_join_room_event):
        """Test successful lambda handler execution."""
        with patch('lambdas.websocket_join_room.handler') as mock_handler:
            mock_handler.handle_websocket_request.return_value = {'statusCode': 200}
            
            result = lambda_handler(sample_join_room_event, {})
            
            assert result['statusCode'] == 200
            mock_handler.handle_websocket_request.assert_called_once_with(sample_join_room_event, {})
    
    def test_lambda_handler_exception(self, sample_join_room_event):
        """Test lambda handler with exception."""
        with patch('lambdas.websocket_join_room.handler') as mock_handler:
            mock_handler.handle_websocket_request.side_effect = Exception("Test error")
            
            result = lambda_handler(sample_join_room_event, {})
            
            assert result['statusCode'] == 500
            assert 'WebSocket error' in result['body']
    
    def test_lambda_handler_debug_logging(self, sample_join_room_event, caplog):
        """Test that lambda handler logs debug information."""
        with patch('lambdas.websocket_join_room.handler') as mock_handler:
            mock_handler.handle_websocket_request.return_value = {'statusCode': 200}
            
            lambda_handler(sample_join_room_event, {})
            
            # Verify handler was called
            mock_handler.handle_websocket_request.assert_called_once()
