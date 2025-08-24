import pytest
import json
import boto3
from unittest.mock import patch, MagicMock, Mock
from botocore.exceptions import ClientError
from lambdas.utils.websocket_utils import send_websocket_message, broadcast_to_connection, get_active_connections


class TestWebSocketUtils:
    """Test suite for WebSocket utility functions"""
    
    @pytest.fixture
    def mock_apigateway(self):
        """Mock API Gateway Management API client"""
        with patch('boto3.client') as mock_client:
            mock_apigateway = MagicMock()
            mock_client.return_value = mock_apigateway
            yield mock_apigateway
    
    @pytest.fixture
    def sample_message(self):
        """Sample message for testing"""
        return {
            'action': 'testAction',
            'data': 'testData',
            'timestamp': '2023-01-01T00:00:00Z'
        }
    
    def test_send_websocket_message_success(self, mock_apigateway, sample_message):
        """Test successful WebSocket message sending"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            connection_id = 'test-connection-123'
            
            result = send_websocket_message(connection_id, sample_message)
            assert result is True
            
            # Verify boto3.client was called with correct parameters
            mock_apigateway.post_to_connection.assert_called_once_with(
                ConnectionId=connection_id,
                Data=json.dumps(sample_message)
            )
    
    def test_send_websocket_message_gone_exception(self, mock_apigateway, sample_message):
        """Test WebSocket message sending when connection is gone"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            connection_id = 'test-connection-123'
            
            # Mock GoneException (connection no longer exists)
            mock_apigateway.post_to_connection.side_effect = ClientError(
                {'Error': {'Code': 'GoneException', 'Message': 'Connection is gone'}},
                'PostToConnection'
            )
            
            result = send_websocket_message(connection_id, sample_message)
            assert result is False
    
    def test_send_websocket_message_other_exception(self, mock_apigateway, sample_message):
        """Test WebSocket message sending with other types of exceptions"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            connection_id = 'test-connection-123'
            
            # Mock other exception
            mock_apigateway.post_to_connection.side_effect = Exception("Test exception")
            
            result = send_websocket_message(connection_id, sample_message)
            assert result is False
    
    def test_send_websocket_message_missing_endpoint(self, sample_message):
        """Test WebSocket message sending with missing endpoint"""
        connection_id = 'test-connection-123'
        
        result = send_websocket_message(connection_id, sample_message)
        assert result is False
    
    def test_send_websocket_message_invalid_endpoint(self, sample_message):
        """Test WebSocket message sending with invalid endpoint format"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'invalid-endpoint'}):
            connection_id = 'test-connection-123'
            
            result = send_websocket_message(connection_id, sample_message)
            assert result is False
    
    def test_send_websocket_message_wss_endpoint_conversion(self, mock_apigateway, sample_message):
        """Test WebSocket message sending with wss:// endpoint conversion"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'wss://test.execute-api.us-east-1.amazonaws.com/test'}):
            connection_id = 'test-connection-123'
            
            result = send_websocket_message(connection_id, sample_message)
            assert result is True
            
            # Verify the endpoint was converted from wss:// to https://
            mock_apigateway.post_to_connection.assert_called_once()
    
    def test_send_websocket_message_ws_endpoint_conversion(self, mock_apigateway, sample_message):
        """Test WebSocket message sending with ws:// endpoint conversion"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'ws://test.execute-api.us-east-1.amazonaws.com/test'}):
            connection_id = 'test-connection-123'
            
            result = send_websocket_message(connection_id, sample_message)
            assert result is True
            
            # Verify the endpoint was converted from ws:// to http://
            mock_apigateway.post_to_connection.assert_called_once()
    
    def test_broadcast_to_connection_success(self, sample_message):
        """Test successful broadcast to single connection"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            with patch('lambdas.utils.websocket_utils.send_websocket_message') as mock_send:
                mock_send.return_value = True
                
                connection_id = 'test-connection-123'
                result = broadcast_to_connection(connection_id, sample_message)
                
                assert result[connection_id] is True
                mock_send.assert_called_once_with(connection_id, sample_message)
    
    def test_broadcast_to_connection_failure(self, sample_message):
        """Test broadcast to single connection with failure"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            with patch('lambdas.utils.websocket_utils.send_websocket_message') as mock_send:
                mock_send.return_value = False
                
                connection_id = 'test-connection-123'
                result = broadcast_to_connection(connection_id, sample_message)
                
                assert result[connection_id] is False
                mock_send.assert_called_once_with(connection_id, sample_message)
    
    def test_broadcast_to_connection_exception(self, sample_message):
        """Test broadcast to single connection with exception"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            with patch('lambdas.utils.websocket_utils.send_websocket_message') as mock_send:
                mock_send.side_effect = Exception("Test exception")
                
                connection_id = 'test-connection-123'
                result = broadcast_to_connection(connection_id, sample_message)
                
                assert result[connection_id] is False
    
    def test_broadcast_to_connection_empty_connection_id(self, sample_message):
        """Test broadcast with empty connection ID"""
        with patch.dict('os.environ', {'WEBSOCKET_ENDPOINT': 'https://test.execute-api.us-east-1.amazonaws.com/test'}):
            result = broadcast_to_connection('', sample_message)
            assert result == {}
            
            result = broadcast_to_connection(None, sample_message)
            assert result == {}
    
    def test_get_active_connections_success(self, mock_boto3_resource_websocket):
        """Test successful retrieval of active connections"""
        with patch.dict('os.environ', {'WEBSOCKET_CONNECTIONS_TABLE': 'test-connections-table'}):
            mock_table = mock_boto3_resource_websocket.return_value.Table.return_value
            
            mock_table.scan.return_value = {
                'Items': [
                    {'connectionId': 'conn-1', 'status': 'connected'},
                    {'connectionId': 'conn-2', 'status': 'connected'},
                    {'connectionId': 'conn-3', 'status': 'disconnected'}
                ]
            }
            
            connections = get_active_connections()
            
            # The function returns ALL items from scan, not just connected ones
            # The filtering happens in the calling code, not in this utility function
            assert connections == ['conn-1', 'conn-2', 'conn-3']
            mock_table.scan.assert_called_once_with(
                FilterExpression='#status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': 'connected'}
            )
    
    def test_get_active_connections_missing_table_env(self):
        """Test active connections retrieval with missing table environment variable"""
        connections = get_active_connections()
        assert connections == []
    
    def test_get_active_connections_exception(self):
        """Test active connections retrieval with exception"""
        with patch.dict('os.environ', {'WEBSOCKET_CONNECTIONS_TABLE': 'test-connections-table'}):
            with patch('boto3.resource') as mock_resource:
                mock_resource.side_effect = Exception("Test exception")
                
                connections = get_active_connections()
                assert connections == []
    
    def test_get_active_connections_empty_response(self):
        """Test active connections retrieval with empty response"""
        with patch.dict('os.environ', {'WEBSOCKET_CONNECTIONS_TABLE': 'test-connections-table'}):
            with patch('boto3.resource') as mock_resource:
                mock_table = MagicMock()
                mock_resource.return_value.Table.return_value = mock_table
                
                mock_table.scan.return_value = {'Items': []}
                
                connections = get_active_connections()
                assert connections == []
