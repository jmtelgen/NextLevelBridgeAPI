import pytest
import json
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError
import sys

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.websocket_disconnect import lambda_handler


class TestWebSocketDisconnect:
    """Test cases for WebSocket disconnect handler."""
    
    @pytest.fixture
    def sample_disconnect_event(self):
        """Sample WebSocket disconnect event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': '$disconnect',
                'requestTimeEpoch': 1640995200000
            }
        }
    
    @pytest.fixture
    def mock_environment(self):
        """Set up test environment variables."""
        env_vars = {
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
    
    def test_lambda_handler_success(self, sample_disconnect_event, mock_environment):
        """Test successful WebSocket disconnect."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful query and delete operations
            mock_table.query.return_value = {
                'Items': [
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'room-1'},
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'room-2'}
                ]
            }
            mock_table.delete_item.return_value = {}
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200
            assert mock_table.query.call_count == 1
            assert mock_table.delete_item.call_count == 2
    
    def test_lambda_handler_missing_connection_id(self, mock_environment):
        """Test disconnect with missing connection ID."""
        event = {
            'requestContext': {
                'routeKey': '$disconnect',
                'requestTimeEpoch': 1640995200000
            }
        }
        
        result = lambda_handler(event, {})
        
        assert result['statusCode'] == 400
    
    def test_lambda_handler_missing_table_env_var(self):
        """Test disconnect with missing table environment variable."""
        # Ensure the environment variable is not set
        if 'WEBSOCKET_CONNECTIONS_TABLE' in os.environ:
            del os.environ['WEBSOCKET_CONNECTIONS_TABLE']
        
        result = lambda_handler({'requestContext': {'connectionId': 'test-123'}}, {})
        
        assert result['statusCode'] == 500
    
    def test_lambda_handler_no_connection_records(self, sample_disconnect_event, mock_environment):
        """Test disconnect when no connection records exist."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock empty query response
            mock_table.query.return_value = {'Items': []}
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200
            mock_table.query.assert_called_once()
            mock_table.delete_item.assert_not_called()
    
    def test_lambda_handler_dynamodb_client_error(self, sample_disconnect_event, mock_environment):
        """Test disconnect with DynamoDB client error."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock query to raise ClientError
            mock_table.query.side_effect = ClientError(
                {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Table not found'}},
                'Query'
            )
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200  # Should handle gracefully
    
    def test_lambda_handler_delete_item_client_error(self, sample_disconnect_event, mock_environment):
        """Test disconnect with delete_item ClientError."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful query
            mock_table.query.return_value = {
                'Items': [
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'room-1'}
                ]
            }
            
            # Mock delete_item to raise ClientError
            mock_table.delete_item.side_effect = ClientError(
                {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Item not found'}},
                'DeleteItem'
            )
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200  # Should handle gracefully
    
    def test_lambda_handler_delete_item_other_error(self, sample_disconnect_event, mock_environment):
        """Test disconnect with delete_item non-ResourceNotFoundException error."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock successful query
            mock_table.query.return_value = {
                'Items': [
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'room-1'}
                ]
            }
            
            # Mock delete_item to raise other ClientError
            mock_table.delete_item.side_effect = ClientError(
                {'Error': {'Code': 'ValidationException', 'Message': 'Invalid key'}},
                'DeleteItem'
            )
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200  # Should handle gracefully
    
    def test_lambda_handler_unexpected_exception(self, sample_disconnect_event, mock_environment):
        """Test disconnect with unexpected exception."""
        with patch('boto3.resource') as mock_resource:
            mock_resource.side_effect = Exception("Unexpected error")
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 500
    
    def test_lambda_handler_multiple_rooms(self, sample_disconnect_event, mock_environment):
        """Test disconnect with connection in multiple rooms."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock query response with multiple rooms
            mock_table.query.return_value = {
                'Items': [
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'room-1'},
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'room-2'},
                    {'connectionId': 'test-connection-123', 'currentRoomId': 'not-joined'}
                ]
            }
            mock_table.delete_item.return_value = {}
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200
            assert mock_table.delete_item.call_count == 3
            
            # Verify delete calls were made with correct keys
            delete_calls = mock_table.delete_item.call_args_list
            expected_keys = [
                {'connectionId': 'test-connection-123', 'currentRoomId': 'room-1'},
                {'connectionId': 'test-connection-123', 'currentRoomId': 'room-2'},
                {'connectionId': 'test-connection-123', 'currentRoomId': 'not-joined'}
            ]
            
            for i, call in enumerate(delete_calls):
                assert call[1]['Key'] == expected_keys[i]
    
    def test_lambda_handler_missing_current_room_id(self, sample_disconnect_event, mock_environment):
        """Test disconnect with missing currentRoomId in connection record."""
        with patch('boto3.resource') as mock_resource:
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            # Mock query response with missing currentRoomId
            mock_table.query.return_value = {
                'Items': [
                    {'connectionId': 'test-connection-123'}  # No currentRoomId
                ]
            }
            mock_table.delete_item.return_value = {}
            
            result = lambda_handler(sample_disconnect_event, {})
            
            assert result['statusCode'] == 200
            # Should use default 'not-joined' value
            mock_table.delete_item.assert_called_once_with(
                Key={'connectionId': 'test-connection-123', 'currentRoomId': 'not-joined'}
            )
