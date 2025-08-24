import pytest
import os
from unittest.mock import patch, MagicMock
from lambdas.utils.db_utils import DatabaseUtils


class TestDatabaseUtils:
    """Test cases for DatabaseUtils class."""
    
    @pytest.fixture
    def db_utils(self):
        """Create a DatabaseUtils instance for testing."""
        return DatabaseUtils()
    
    def test_init(self, db_utils):
        """Test DatabaseUtils initialization."""
        assert db_utils._websocket_connections_table is None
    
    def test_get_table_success(self, db_utils):
        """Test successful table retrieval."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['TEST_TABLE'] = 'test-table-name'
            table = db_utils.get_table('TEST_TABLE')
            
            assert table is not None
            mock_dynamodb.Table.assert_called_once_with('test-table-name')
    
    def test_get_table_missing_env_var(self, db_utils):
        """Test table retrieval with missing environment variable."""
        if 'MISSING_TABLE' in os.environ:
            del os.environ['MISSING_TABLE']
        
        with pytest.raises(ValueError, match="MISSING_TABLE environment variable not set"):
            db_utils.get_table('MISSING_TABLE')
    
    def test_websocket_connections_table_property(self, db_utils):
        """Test websocket connections table property caching."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # First access should call get_table
            table1 = db_utils.websocket_connections_table
            assert table1 is not None
            
            # Second access should use cached value
            table2 = db_utils.websocket_connections_table
            assert table2 is table1
            # Should not call get_table again (cached)
            assert db_utils._websocket_connections_table is not None
    
    def test_update_user_room_success(self, db_utils):
        """Test successful user room update."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock scan response
            mock_table.scan.return_value = {
                'Items': [
                    {
                        'connectionId': 'conn-1',
                        'userId': 'user-123',
                        'currentRoomId': 'old-room',
                        'status': 'connected'
                    }
                ]
            }
            
            # Mock successful operations
            mock_table.delete_item.return_value = {}
            mock_table.put_item.return_value = {}
            
            result = db_utils.update_user_room('user-123', 'new-room')
            assert result is True
            
            # Verify delete_item was called
            mock_table.delete_item.assert_called_once_with(
                Key={'connectionId': 'conn-1', 'currentRoomId': 'old-room'}
            )
            
            # Verify put_item was called with updated room
            mock_table.put_item.assert_called_once()
            put_item_call = mock_table.put_item.call_args
            assert put_item_call[1]['Item']['currentRoomId'] == 'new-room'
    
    def test_update_user_room_no_connections(self, db_utils):
        """Test user room update when no connections exist."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock empty scan response
            mock_table.scan.return_value = {'Items': []}
            
            result = db_utils.update_user_room('user-123', 'new-room')
            assert result is False
    
    def test_update_user_room_exception(self, db_utils):
        """Test user room update with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock scan to raise exception
            mock_table.scan.side_effect = Exception("Test exception")
            
            result = db_utils.update_user_room('user-123', 'new-room')
            assert result is False
    
    def test_get_room_connection_success(self, db_utils):
        """Test successful room connection retrieval."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            mock_table.scan.return_value = {
                'Items': [
                    {'connectionId': 'conn-1', 'userId': 'user-123', 'status': 'connected'},
                    {'connectionId': 'conn-2', 'userId': 'user-123', 'status': 'connected'}
                ]
            }
            
            connection = db_utils.get_room_connection('user-123')
            assert connection == 'conn-1'
    
    def test_get_room_connection_no_user_id(self, db_utils):
        """Test room connection retrieval with no user ID."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock empty scan response
            mock_table.scan.return_value = {'Items': []}
            
            connection = db_utils.get_room_connection('')
            assert connection is None
    
    def test_get_room_connection_no_connections(self, db_utils):
        """Test room connection retrieval with no connections."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock empty scan response
            mock_table.scan.return_value = {'Items': []}
            
            connection = db_utils.get_room_connection('user-123')
            assert connection is None
    
    def test_get_room_connection_exception(self, db_utils):
        """Test room connection retrieval with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock scan to raise exception
            mock_table.scan.side_effect = Exception("Test exception")
            
            connection = db_utils.get_room_connection('user-123')
            assert connection is None
    

    

    

    

    
    def test_find_room_by_id_success(self, db_utils):
        """Test successful room finding by ID."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            mock_table.scan.return_value = {
                'Count': 1,
                'Items': [
                    {
                        'roomId': 'room-123',
                        'ownerId': 'user-123',
                        'state': 'waiting'
                    }
                ]
            }
            
            room = db_utils.find_room_by_id('room-123', mock_table)
            assert room is not None
            assert room['roomId'] == 'room-123'
            assert room['ownerId'] == 'user-123'
    
    def test_find_room_by_id_not_found(self, db_utils):
        """Test room finding when room doesn't exist."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            mock_table.scan.return_value = {'Count': 0, 'Items': []}
            
            room = db_utils.find_room_by_id('room-123', mock_table)
            assert room is None
    
    def test_find_room_by_id_exception(self, db_utils):
        """Test room finding with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            mock_table.scan.side_effect = Exception("Test exception")
            
            room = db_utils.find_room_by_id('room-123', mock_table)
            assert room is None
    
    def test_create_connection_record_success(self, db_utils):
        """Test successful connection record creation."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock successful put_item operation
            mock_table.put_item.return_value = {}
            
            result = db_utils.create_connection_record(
                'conn-123', 'user-123', 'room-123', '2023-01-01T00:00:00Z'
            )
            assert result is True
            
            mock_table.put_item.assert_called_once()
            put_item_call = mock_table.put_item.call_args
            item = put_item_call[1]['Item']
            assert item['connectionId'] == 'conn-123'
            assert item['userId'] == 'user-123'
            assert item['currentRoomId'] == 'not-joined'
    
    def test_create_connection_record_exception(self, db_utils):
        """Test connection record creation with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock put_item to raise exception
            mock_table.put_item.side_effect = Exception("Test error")
            
            result = db_utils.create_connection_record(
                'conn-123', 'user-123', 'room-123', '2023-01-01T00:00:00Z'
            )
            assert result is False
    
    def test_delete_connection_record_success(self, db_utils):
        """Test successful connection record deletion."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock successful delete_item operation
            mock_table.delete_item.return_value = {}
            
            result = db_utils.delete_connection_record('conn-123', 'room-123')
            assert result is True
            
            mock_table.delete_item.assert_called_once_with(
                Key={'connectionId': 'conn-123', 'currentRoomId': 'room-123'}
            )
    
    def test_delete_connection_record_exception(self, db_utils):
        """Test connection record deletion with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock delete_item to raise exception
            mock_table.delete_item.side_effect = Exception("Test error")
            
            result = db_utils.delete_connection_record('conn-123', 'room-123')
            assert result is False
    
    def test_get_active_room_count_success(self, db_utils):
        """Test successful active room count retrieval."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            mock_table.scan.return_value = {
                'Items': [
                    {'currentRoomId': 'room-1', 'status': 'connected'},
                    {'currentRoomId': 'room-2', 'status': 'connected'},
                    {'currentRoomId': 'not-joined', 'status': 'connected'},
                    {'currentRoomId': 'room-3', 'status': 'connected'}
                ]
            }
            
            count = db_utils.get_active_room_count()
            assert count == 3  # room-1, room-2, room-3 (excluding 'not-joined')
    
    def test_get_active_user_count_success(self, db_utils):
        """Test successful active user count retrieval."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            mock_table.scan.return_value = {
                'Items': [
                    {'userId': 'user-1', 'status': 'connected'},
                    {'userId': 'user-2', 'status': 'disconnected'},
                    {'userId': 'user-3', 'status': 'connected'},
                    {'userId': 'user-4', 'status': 'connected'}
                ]
            }
            
            count = db_utils.get_active_user_count()
            assert count == 3  # user-1, user-3, user-4 (only connected)
    
    def test_get_connection_stats_success(self, db_utils):
        """Test successful connection stats retrieval."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            mock_table.scan.return_value = {
                'Items': [
                    {'userId': 'user-1', 'status': 'connected', 'currentRoomId': 'room-1'},
                    {'userId': 'user-2', 'status': 'connected', 'currentRoomId': 'room-2'},
                    {'userId': 'user-3', 'status': 'connected', 'currentRoomId': 'room-1'},
                    {'userId': 'user-4', 'status': 'disconnected', 'currentRoomId': 'room-3'}
                ]
            }
            
            stats = db_utils.get_connection_stats()
            assert stats['activeUserCount'] == 3
            assert stats['activeRoomCount'] == 2  # room-1, room-2 (excluding room-3 with disconnected user)
    
    def test_pagination_handling(self, db_utils):
        """Test pagination handling in scan operations."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # First scan returns some items and LastEvaluatedKey
            mock_table.scan.side_effect = [
                {
                    'Items': [
                        {'userId': 'user-1', 'status': 'connected', 'currentRoomId': 'room-1'}
                    ],
                    'LastEvaluatedKey': {'connectionId': 'conn-1'}
                },
                {
                    'Items': [
                        {'userId': 'user-2', 'status': 'connected', 'currentRoomId': 'room-2'}
                    ]
                    # No LastEvaluatedKey means end of results
                }
            ]
            
            count = db_utils.get_active_room_count()
            assert count == 2  # room-1 and room-2
            assert mock_table.scan.call_count == 2
    
    def test_get_active_room_count_exception(self, db_utils):
        """Test active room count retrieval with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock scan to raise exception
            mock_table.scan.side_effect = Exception("Test exception")
            
            count = db_utils.get_active_room_count()
            assert count == 0
    
    def test_get_active_user_count_exception(self, db_utils):
        """Test active user count retrieval with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock scan to raise exception
            mock_table.scan.side_effect = Exception("Test exception")
            
            count = db_utils.get_active_user_count()
            assert count == 0
    
    def test_get_connection_stats_exception(self, db_utils):
        """Test connection stats retrieval with exception."""
        with patch.object(db_utils, 'dynamodb') as mock_dynamodb:
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            
            os.environ['WEBSOCKET_CONNECTIONS_TABLE'] = 'connections-table'
            
            # Mock scan to raise exception
            mock_table.scan.side_effect = Exception("Test exception")
            
            stats = db_utils.get_connection_stats()
            assert stats['activeUserCount'] == 0
            assert stats['activeRoomCount'] == 0
