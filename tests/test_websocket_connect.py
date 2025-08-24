import pytest
import json
from unittest.mock import patch, MagicMock
import sys
import os

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.websocket_connect import WebSocketConnectHandler, lambda_handler


class TestWebSocketConnectHandler:
    """Test cases for WebSocketConnectHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create a WebSocketConnectHandler instance for testing."""
        return WebSocketConnectHandler()
    
    @pytest.fixture
    def sample_connect_event(self):
        """Sample WebSocket connect event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': '$connect',
                'requestTimeEpoch': 1640995200000
            },
            'queryStringParameters': {
                'userId': 'test-user-123',
                'userName': 'TestUser'
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
    
    def test_init(self, handler):
        """Test WebSocketConnectHandler initialization."""
        assert handler is not None
    
    def test_process_websocket_request_success(self, handler, sample_connect_event, mock_environment):
        """Test successful WebSocket connect request processing."""
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.return_value = True
            
            result = handler.process_websocket_request(sample_connect_event, {})
            
            assert result['statusCode'] == 200
            mock_db_utils.create_connection_record.assert_called_once_with(
                connection_id='test-connection-123',
                user_id='test-user-123',
                user_name='TestUser',
                request_time=1640995200000
            )
    
    def test_process_websocket_request_missing_connection_id(self, handler):
        """Test WebSocket connect request with missing connection ID."""
        event = {
            'requestContext': {
                'routeKey': '$connect',
                'requestTimeEpoch': 1640995200000
            },
            'queryStringParameters': {
                'userId': 'test-user-123',
                'userName': 'TestUser'
            }
        }
        
        result = handler.process_websocket_request(event, {})
        
        assert result['statusCode'] == 400
        assert 'Missing connection ID' in result.get('body', '')
    
    def test_process_websocket_request_db_failure(self, handler, sample_connect_event, mock_environment):
        """Test WebSocket connect request when database operation fails."""
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.return_value = False
            
            result = handler.process_websocket_request(sample_connect_event, {})
            
            assert result['statusCode'] == 500
            assert 'Failed to create connection record' in result.get('body', '')
    
    def test_process_websocket_request_missing_user_info(self, handler, mock_environment):
        """Test WebSocket connect request with missing user info."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': '$connect',
                'requestTimeEpoch': 1640995200000
            }
            # No queryStringParameters
        }
        
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.return_value = True
            
            result = handler.process_websocket_request(event, {})
            
            assert result['statusCode'] == 200
            # Should handle missing user info gracefully
            mock_db_utils.create_connection_record.assert_called_once_with(
                connection_id='test-connection-123',
                user_id=None,
                user_name=None,
                request_time=1640995200000
            )
    
    def test_process_websocket_request_missing_request_time(self, handler, mock_environment):
        """Test WebSocket connect request with missing request time."""
        event = {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': '$connect'
                # No requestTimeEpoch
            },
            'queryStringParameters': {
                'userId': 'test-user-123',
                'userName': 'TestUser'
            }
        }
        
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.return_value = True
            
            result = handler.process_websocket_request(event, {})
            
            assert result['statusCode'] == 200
            # Should handle missing request time gracefully
            mock_db_utils.create_connection_record.assert_called_once_with(
                connection_id='test-connection-123',
                user_id='test-user-123',
                user_name='TestUser',
                request_time=None
            )


class TestWebSocketConnectLambda:
    """Test cases for the lambda_handler function."""
    
    @pytest.fixture
    def sample_connect_event(self):
        """Sample WebSocket connect event."""
        return {
            'requestContext': {
                'connectionId': 'test-connection-123',
                'routeKey': '$connect',
                'requestTimeEpoch': 1640995200000
            },
            'queryStringParameters': {
                'userId': 'test-user-123',
                'userName': 'TestUser'
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
    
    def test_lambda_handler_success(self, sample_connect_event, mock_environment):
        """Test successful lambda handler execution."""
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.return_value = True
            
            result = lambda_handler(sample_connect_event, {})
            
            assert result['statusCode'] == 200
    
    def test_lambda_handler_exception(self, sample_connect_event, mock_environment):
        """Test lambda handler with exception."""
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.side_effect = Exception("Test error")
            
            result = lambda_handler(sample_connect_event, {})
            
            assert result['statusCode'] == 500
            assert 'Test error' in result['body']
    
    def test_lambda_handler_debug_logging(self, sample_connect_event, mock_environment, capsys):
        """Test that lambda handler logs debug information."""
        with patch('lambdas.websocket_connect.db_utils') as mock_db_utils:
            mock_db_utils.create_connection_record.return_value = True
            
            lambda_handler(sample_connect_event, {})
            
            captured = capsys.readouterr()
            assert 'LAMBDA HANDLER CALLED with event:' in captured.out
            assert 'Event type:' in captured.out
            assert 'Event keys:' in captured.out
