import pytest
import json
import copy
from unittest.mock import patch, MagicMock, call
from lambdas.api.websocket.websocket_make_bid import WebSocketMakeBidHandler, VALID_BIDS
from lambdas.core.game import runtime
from lambdas.shared.utils.seat_filtering import create_seat_based_response


class TestWebSocketMakeBid:
    """Comprehensive test suite for WebSocket make bid functionality"""
    
    # ==================== FIXTURES ====================
    
    @pytest.fixture
    def handler(self):
        """Create a WebSocketMakeBidHandler instance for testing"""
        return WebSocketMakeBidHandler()
    
    @pytest.fixture
    def mock_context(self):
        """Sample Lambda context"""
        context = MagicMock()
        context.function_name = 'websocket-make-bid'
        context.aws_request_id = 'test-request-123'
        return context
    
    @pytest.fixture
    def base_room_data(self):
        """Base room data in bidding phase"""
        return {
            'roomId': 'room-123',
            'ownerId': 'user-123',
            'state': 'bidding',
            'seats': {
                'North': 'user-123',
                'East': 'ROBOT_1',
                'South': 'user-456',
                'West': 'ROBOT_2'
            },
            'presence': {
                'North': {'userId': 'user-123', 'connections': {'conn-user-123': 4102444800}},
                'South': {'userId': 'user-456', 'connections': {'conn-user-456': 4102444800}},
            },
            'gameData': {
                'currentPhase': 'bidding',
                'turn': 'North',
                'dealer': 'North',
                'vulnerability': 'None',
                'bids': [],
                'hands': {
                    'North': ['AS', 'KH', 'QD', 'JC'],
                    'East': ['2S', '3H', '4D', '5C'],
                    'South': ['6S', '7H', '8D', '9C'],
                    'West': ['TS', 'JH', 'QD', 'KC']
                },
                'tricks': []
            }
        }
    
    @pytest.fixture
    def mock_event_factory(self, mock_db_utils):
        """Factory for creating WebSocket events"""
        def _create_event(user_id='user-123', room_id='room-123', bid='1H', route_key='makeBid'):
            mock_db_utils.websocket_connections_table.query.return_value = {'Items': [{
                'userId': user_id, 'status': 'connected',
                'authExpiresAt': 4102444800, 'authType': 'guest',
            }]}
            return {
                'requestContext': {
                    'routeKey': route_key,
                    'connectionId': 'test-connection-123',
                    'domainName': 'test.execute-api.us-east-1.amazonaws.com',
                    'stage': 'test'
                },
                'body': json.dumps({
                    'userId': user_id,
                    'roomId': room_id,
                    'bid': bid
                })
            }
        return _create_event
    
    @pytest.fixture(autouse=True)
    def mock_time(self):
        """Mock time.time() for consistent timestamps"""
        with patch('lambdas.core.game.rules.time.time') as mock_t:
            mock_t.return_value = 1234567890.123
            yield mock_t
    
    @pytest.fixture(autouse=True)
    def mock_db_utils(self, base_room_data):
        """Mock database utilities"""
        with patch('lambdas.api.websocket.websocket_make_bid.db_utils') as mock_db:
            mock_table = MagicMock()
            mock_db.get_table.return_value = mock_table
            mock_db.find_room_by_id.return_value = copy.deepcopy(base_room_data)
            mock_db.get_room_connection.return_value = 'conn-123'
            mock_db.get_user_connections.side_effect = lambda user: [f'conn-{user}']
            mock_db.get_user_connection_records.side_effect = lambda user: [{
                'userId': user, 'connectionId': f'conn-{user}', 'authExpiresAt': 4102444800,
                'authType': 'guest', 'status': 'connected',
            }]
            mock_db.websocket_connections_table.query.return_value = {'Items': [{
                'userId': 'user-123', 'status': 'connected',
                'authExpiresAt': 4102444800, 'authType': 'guest',
            }]}
            def persist_snapshot(**kwargs):
                mock_table.put_item.call_args.kwargs['Item'] = copy.deepcopy(kwargs['Item'])
            mock_table.put_item.side_effect = persist_snapshot
            yield mock_db
    
    @pytest.fixture(autouse=True)
    def mock_robot_utils(self):
        """Mock robot utilities"""
        mocks = {}
        with patch('lambdas.core.game.runtime.is_robot_seat') as mock_is_robot, \
             patch('lambdas.core.game.runtime.execute_robot_bid') as mock_exec_bid, \
             patch('lambdas.core.game.runtime.execute_robot_card_play') as mock_exec_play:
            mock_get_turns = MagicMock()  # Legacy hints must not drive authoritative turns.
            mock_next_seat = MagicMock()
            
            # Default implementations
            mock_is_robot.side_effect = lambda x: x and x.startswith('ROBOT_')
            mock_get_turns.return_value = []
            mock_exec_bid.return_value = 'pass'
            mock_exec_play.return_value = '2S'  # Card that's in East's hand in base_room_data
            mock_next_seat.side_effect = lambda seat: {
                'North': 'East', 'East': 'South', 'South': 'West', 'West': 'North'
            }.get(seat, 'North')
            
            mocks['is_robot_seat'] = mock_is_robot
            mocks['get_robot_turns_sequence'] = mock_get_turns
            mocks['execute_robot_bid'] = mock_exec_bid
            mocks['execute_robot_card_play'] = mock_exec_play
            mocks['get_next_seat'] = mock_next_seat
            
            yield mocks
    
    @pytest.fixture(autouse=True)
    def mock_broadcast(self):
        """Mock broadcast and seat filtering functions"""
        mocks = {}
        with patch('lambdas.api.websocket.websocket_make_bid.broadcast_to_connection') as mock_broadcast_conn, \
             patch('lambdas.core.game.runtime.publish', wraps=runtime.publish) as mock_broadcast_game, \
             patch('lambdas.core.game.runtime.create_seat_based_response',
                   wraps=create_seat_based_response) as mock_create_response:
            
            mocks['broadcast_to_connection'] = mock_broadcast_conn
            mocks['broadcast_game_update'] = mock_broadcast_game
            mocks['create_seat_based_response'] = mock_create_response
            
            yield mocks
    
    # ==================== A. REQUEST VALIDATION TESTS ====================
    
    def test_invalid_route_key(self, handler, mock_event_factory, mock_context):
        """Test that invalid route key returns 400 error"""
        event = mock_event_factory(route_key='invalidRoute')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'route' in body['error'].lower()
    
    def test_missing_user_id(self, handler, mock_context):
        """Signed connection supplies identity when redundant userId is omitted."""
        event = {
            'requestContext': {'routeKey': 'makeBid', 'connectionId': 'conn-123'},
            'body': json.dumps({'roomId': 'room-123', 'bid': '1H'})
        }
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['seat'] == 'North'
        assert body['privateState']['seat'] == 'North'
    
    def test_missing_room_id(self, handler, mock_context):
        """Test that missing roomId returns 400 error"""
        event = {
            'requestContext': {'routeKey': 'makeBid', 'connectionId': 'conn-123'},
            'body': json.dumps({'userId': 'user-123', 'bid': '1H'})
        }
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'roomId' in body['error']
    
    def test_missing_bid(self, handler, mock_context):
        """Test that missing bid returns 400 error"""
        event = {
            'requestContext': {'routeKey': 'makeBid', 'connectionId': 'conn-123'},
            'body': json.dumps({'userId': 'user-123', 'roomId': 'room-123'})
        }
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'bid' in body['error']
    
    def test_invalid_bid_value(self, handler, mock_event_factory, mock_context):
        """Test that invalid bid value returns 400 error"""
        event = mock_event_factory(bid='invalid_bid')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid bid' in body['error']
    
    def test_room_not_found(self, handler, mock_event_factory, mock_context, mock_db_utils, mock_robot_utils, mock_broadcast, mock_time):
        """Test that non-existent room returns 404 error"""
        mock_db_utils.find_room_by_id.return_value = None
        event = mock_event_factory()
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'does not exist' in body['error']
    
    def test_room_not_in_bidding_phase(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test that room not in bidding phase returns 400 error"""
        room_data = copy.deepcopy(base_room_data)
        room_data['state'] = 'playing'
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory()
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'not in bidding phase' in body['error']
    
    def test_user_not_in_room(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test that user not in room returns 400 error"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(user_id='unknown-user')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert 'not seated' in body['error']
    
    def test_not_users_turn(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test that bidding out of turn returns 400 error"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['turn'] = 'East'  # Not user's turn
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory()
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'not your turn' in body['error'].lower()
    
    # ==================== B. HUMAN BIDDING TESTS ====================
    
    def test_human_makes_opening_bid(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test human makes valid opening bid (1H)"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        # Verify bid was added
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[0][1]['Item']
        assert len(saved_room['gameData']['bids']) == 1
        assert saved_room['gameData']['bids'][0]['bid'] == '1H'
        assert saved_room['gameData']['bids'][0]['seat'] == 'North'
    
    def test_human_makes_pass_bid(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test human makes pass bid"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[0][1]['Item']
        assert saved_room['gameData']['bids'][0]['bid'] == 'pass'
    
    def test_bid_entry_structure(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test bid entry has correct structure with seat, bid, and timestamp"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='1S')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[0][1]['Item']
        bid_entry = saved_room['gameData']['bids'][0]
        assert 'seat' in bid_entry
        assert 'bid' in bid_entry
        assert 'timestamp' in bid_entry
        assert bid_entry['seat'] == 'North'
        assert bid_entry['bid'] == '1S'
        assert bid_entry['timestamp'] == 1234567890123  # From mock_time
    
    def test_turn_advances_after_bid(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test turn advances to next seat after bid"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['turn'] = 'North'
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='1C')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[0][1]['Item']
        assert saved_room['gameData']['turn'] == 'East'
    
    def test_room_saved_to_database(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test room is saved to database after bid"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='1D')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        # Verify put_item was called
        assert mock_db_utils.get_table.return_value.put_item.called
        assert mock_db_utils.get_table.return_value.put_item.call_count >= 1
    
    # ==================== C. SINGLE ROBOT BIDDING TESTS ====================
    
    def test_single_robot_after_human_bid(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test one robot bids after human"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = '1S'
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        # Verify robot bid was executed
        assert mock_robot_utils['execute_robot_bid'].called
        mock_robot_utils['execute_robot_bid'].assert_called_once()
    
    def test_execute_robot_bid_called_with_correct_parameters(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test execute_robot_bid is called with correct room_data and seat"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = 'pass'
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        # Verify parameters
        call_args = mock_robot_utils['execute_robot_bid'].call_args
        assert call_args[0][1] == 'East'  # Second parameter is robot_seat
        # Verify room_data has the human's bid
        room_arg = call_args[0][0]
        assert 'gameData' in room_arg
        assert len(room_arg['gameData']['bids']) >= 1
    
    def test_robot_sees_previous_bids(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test robot receives room data with all previous bids (room refreshed from DB)"""
        room_data = copy.deepcopy(base_room_data)
        
        # Create multiple room states for all the refreshes
        room_states = [copy.deepcopy(room_data) for _ in range(5)]
        mock_db_utils.find_room_by_id.side_effect = room_states
        
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = 'pass'
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        first_robot = mock_robot_utils['execute_robot_bid'].call_args[0][0]
        assert first_robot['gameData']['bids'][0]['bid'] == '1H'
        assert mock_db_utils.get_table.return_value.put_item.call_count >= 2
    
    def test_robot_bid_added_to_game_data(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test robot bid is added to gameData.bids"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = '1S'
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        # Get the last saved room state
        last_put_call = mock_db_utils.get_table.return_value.put_item.call_args_list[-1]
        saved_room = last_put_call[1]['Item']
        # Should have human bid + robot bid
        assert len(saved_room['gameData']['bids']) == 2
        assert saved_room['gameData']['bids'][0]['bid'] == '1H'
        assert saved_room['gameData']['bids'][0]['seat'] == 'North'
        assert saved_room['gameData']['bids'][1]['bid'] == '1S'
        assert saved_room['gameData']['bids'][1]['seat'] == 'East'
    
    # ==================== D. MULTIPLE CONSECUTIVE ROBOT TURNS ====================
    
    def test_multiple_consecutive_robots(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test human bids, then 2 consecutive robots bid"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        
        # Setup multiple room states for refreshes
        room_states = []
        for i in range(5):  # Initial + refreshes
            state = copy.deepcopy(room_data)
            room_states.append(state)
        mock_db_utils.find_room_by_id.side_effect = room_states
        
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['1S', '2H']
        event = mock_event_factory(bid='1D')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        # Verify execute_robot_bid called twice
        assert mock_robot_utils['execute_robot_bid'].call_count == 2
    
    def test_room_refreshed_before_each_robot(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test room is refreshed from DB before each robot turn"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        room_data['presence']['West'] = room_data['presence'].pop('South')
        
        room_states = [copy.deepcopy(room_data) for _ in range(5)]
        mock_db_utils.find_room_by_id.side_effect = room_states
        
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['pass', 'pass']
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        saves = mock_db_utils.get_table.return_value.put_item.call_args_list
        assert len(saves) == 3
        assert [len(entry.kwargs['Item']['gameData']['bids']) for entry in saves] == [1, 2, 3]
        assert all('ConditionExpression' in entry.kwargs for entry in saves)
    
    def test_second_robot_sees_first_robot_bid(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test second robot sees first robot's bid in bid history"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        
        # Track bid history through calls
        call_count = [0]
        def track_bids(*args, **kwargs):
            call_count[0] += 1
            state = copy.deepcopy(room_data)
            # Add bids progressively
            if call_count[0] == 1:
                state['gameData']['bids'] = []
            elif call_count[0] >= 2:
                state['gameData']['bids'] = [
                    {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123}
                ]
            if call_count[0] >= 3:
                state['gameData']['bids'].append(
                    {'seat': 'East', 'bid': '1S', 'timestamp': 1234567890123}
                )
            return state
        
        mock_db_utils.find_room_by_id.side_effect = track_bids
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['1S', '2H']
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Verify second execute_robot_bid call received updated room data
        assert mock_robot_utils['execute_robot_bid'].call_count == 2
        # Both robots should have been called with proper parameters
        first_call = mock_robot_utils['execute_robot_bid'].call_args_list[0]
        second_call = mock_robot_utils['execute_robot_bid'].call_args_list[1]
        assert first_call[0][1] == 'East'
        assert second_call[0][1] == 'South'
    
    def test_each_robot_bid_recorded(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test each robot bid is recorded separately in gameData"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        
        # Track state through saves
        saved_state = [None]
        def save_room(Item, **kwargs):
            saved_state[0] = copy.deepcopy(Item)
        
        def get_room(*args):
            if saved_state[0]:
                return copy.deepcopy(saved_state[0])
            return copy.deepcopy(room_data)
        
        mock_db_utils.get_table.return_value.put_item.side_effect = save_room
        mock_db_utils.find_room_by_id.side_effect = get_room
        
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['1S', '1NT']
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Get final room state from saved_state
        assert saved_state[0] is not None
        saved_room = saved_state[0]
        # Should have 3 bids: human + 2 robots
        assert len(saved_room['gameData']['bids']) == 3
        assert saved_room['gameData']['bids'][0]['bid'] == '1H'
        assert saved_room['gameData']['bids'][1]['bid'] == '1S'
        assert saved_room['gameData']['bids'][2]['bid'] == '1NT'
    
    def test_execute_robot_bid_called_twice_correct_params(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test execute_robot_bid called twice with correct parameters"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        
        room_states = [copy.deepcopy(room_data) for _ in range(5)]
        mock_db_utils.find_room_by_id.side_effect = room_states
        
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['pass', 'pass']
        event = mock_event_factory(bid='1C')
        
        response = handler.process_websocket_request(event, mock_context)
        
        calls = mock_robot_utils['execute_robot_bid'].call_args_list
        assert len(calls) == 2
        assert calls[0][0][1] == 'East'
        assert calls[1][0][1] == 'South'
    
    # ==================== E. BIDDING END - ALL PASS ====================
    
    def test_four_consecutive_passes_ends_bidding(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test four consecutive passes ends bidding"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'  # Make West the current user
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['gameData']['currentPhase'] == 'completed'
    
    def test_all_pass_sets_phase_completed(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test all pass sets gameData.currentPhase to 'completed'"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['gameData']['currentPhase'] == 'completed'
        assert saved_room['gameData']['gameResult'] == 'noWinner'
    
    def test_all_pass_sets_no_winner(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test all pass sets gameData.gameResult to 'noWinner'"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['gameData']['gameResult'] == 'noWinner'
        assert saved_room['gameData']['gameEndReason'] == 'allPass'
    
    def test_all_pass_sets_room_state_completed(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test all pass sets room.state to 'completed'"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['state'] == 'completed'
    
    # ==================== F. BIDDING END - CONTRACT ESTABLISHED ====================
    
    def test_three_passes_after_contract(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test three passes after contract establishes contract (1H-P-P-P)"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['gameData']['currentPhase'] == 'playing'
    
    def test_contract_sets_phase_playing(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test contract established sets gameData.currentPhase to 'playing'"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1S', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['gameData']['currentPhase'] == 'playing'
        assert saved_room['state'] == 'playing'
    
    def test_contract_sets_room_state_playing(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test contract established sets room.state to 'playing'"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1C', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['state'] == 'playing'
    
    def test_contract_sets_declarer_and_leader(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test contract established sets declarer and opening leader"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1D', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert 'declarer' in saved_room['gameData']
        assert 'openingLeader' in saved_room['gameData']
        assert saved_room['gameData']['declarer'] == 'North'
        assert saved_room['gameData']['openingLeader'] == 'East'
    
    def test_contract_stored_in_game_data(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test contract is stored in gameData"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '2H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        assert saved_room['gameData']['contract'] == '2H'
    
    # ==================== G. DECLARER/OPENING LEADER DETERMINATION ====================
    
    def test_declarer_simple_case(self, handler):
        """Test simple case: 1H by North, all pass → North declarer, East leads"""
        bids = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'North'
        assert leader == 'East'
    
    def test_declarer_partners_same_suit(self, handler):
        """Test partners bid same suit: North 1H, South 3H → North declarer"""
        bids = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': '3H', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'North'  # First to bid hearts on winning team
        assert leader == 'East'
    
    def test_declarer_opponents_same_suit(self, handler):
        """Test opponents bid same suit: proper team determination"""
        bids = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': '2H', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        # East made final contract (2H) and was first to bid H on their team
        assert declarer == 'East'
        assert leader == 'South'
    
    def test_declarer_nt_contract(self, handler):
        """Test NT contract: 1NT by South → South declarer"""
        bids = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': '1NT', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'South'
        assert leader == 'West'
    
    def test_declarer_major_suit(self, handler):
        """Test major suit: 1S by East → East declarer"""
        bids = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': '1S', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'East'
        assert leader == 'South'
    
    def test_declarer_minor_suit(self, handler):
        """Test minor suit: 2C by West → West declarer"""
        bids = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': '2C', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'West'
        assert leader == 'North'
    
    def test_declarer_with_double(self, handler):
        """Test doubled contract: 1H-X-P-P-P → declarer still by suit"""
        bids = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'double', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'North'
        assert leader == 'East'
    
    def test_declarer_with_redouble(self, handler):
        """Test redoubled contract: 1H-X-XX-P-P-P → declarer still by suit"""
        bids = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'double', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'redouble', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        assert declarer == 'North'
        assert leader == 'East'
    
    def test_declarer_complex_bidding(self, handler):
        """Test complex: 1C-1H-2C-2H-P-P-P → 2H wins, first H bidder on team"""
        bids = [
            {'seat': 'North', 'bid': '1C', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': '2C', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': '2H', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        # 2H is final contract, East first bid H on E/W team
        assert declarer == 'East'
        assert leader == 'South'
    
    def test_declarer_multiple_suits(self, handler):
        """Test multiple suits: proper suit tracking for final contract"""
        bids = [
            {'seat': 'North', 'bid': '1C', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': '1D', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': '1S', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': '2S', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        
        declarer, leader = handler._determine_declarer_and_leader(bids)
        
        # 2S is final, West first bid S on N/S team? No, West is on E/W.
        # North bid 2S, first S bidder on N/S team... West bid 1S first overall
        # Final is 2S by North, West first bid spades but they're opponents
        # North's partner South never bid spades, so North is declarer
        assert declarer == 'North'
        assert leader == 'East'
    
    def test_declarer_opening_leader_clockwise(self, handler):
        """Test opening leader is always left (clockwise) of declarer"""
        # North declarer → East leads
        bids = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        declarer, leader = handler._determine_declarer_and_leader(bids)
        assert declarer == 'North' and leader == 'East'
        
        # East declarer → South leads
        bids = [
            {'seat': 'East', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'West', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        declarer, leader = handler._determine_declarer_and_leader(bids)
        assert declarer == 'East' and leader == 'South'
    
    def test_declarer_all_positions(self, handler):
        """Test all four declarer positions work correctly"""
        # Test all four seats as declarer
        for seat, expected_leader in [('North', 'East'), ('East', 'South'), ('South', 'West'), ('West', 'North')]:
            bids = [
                {'seat': seat, 'bid': '1NT', 'timestamp': 1234567890123},
                {'seat': 'North' if seat != 'North' else 'East', 'bid': 'pass', 'timestamp': 1234567890123},
                {'seat': 'East' if seat != 'East' else 'South', 'bid': 'pass', 'timestamp': 1234567890123},
                {'seat': 'South' if seat != 'South' else 'West', 'bid': 'pass', 'timestamp': 1234567890123}
            ]
            declarer, leader = handler._determine_declarer_and_leader(bids)
            assert declarer == seat
            assert leader == expected_leader
    
    # ==================== H. ROBOT OPENING LEAD ====================

    def _resume_opening_lead(self, mock_db_utils, mock_broadcast, mock_context):
        saved = copy.deepcopy(mock_db_utils.get_table.return_value.put_item.call_args.kwargs['Item'])
        pending = saved['gameData']['pendingAction']
        assert pending['kind'] == 'robotCard'
        assert saved['gameData']['currentTrick'] == []
        mock_db_utils.find_room_by_id.return_value = saved
        tick = {'roomId': saved['roomId'], 'revision': saved['revision'], **pending}
        with patch('lambdas.core.game.runtime.now_ms', return_value=pending['dueAt']):
            runtime.process_due_tick(
                mock_db_utils, mock_broadcast['broadcast_to_connection'], tick, mock_context)
    
    def test_robot_opening_lead_when_leader_is_robot(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test robot plays opening lead when opening leader is a robot"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',  # North will be declarer
            'East': 'ROBOT_1',    # East is robot and will be opening leader
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['execute_robot_card_play'].return_value = '2S'  # Card in East's hand
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        mock_robot_utils['execute_robot_card_play'].assert_not_called()
        self._resume_opening_lead(mock_db_utils, mock_broadcast, mock_context)
        mock_robot_utils['execute_robot_card_play'].assert_called_once()
    
    def test_robot_opening_lead_correct_parameters(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test execute_robot_card_play called with correct parameters"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1S', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats']['North'] = 'user-456'
        room_data['seats']['West'] = 'user-123'
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['execute_robot_card_play'].return_value = '2S'
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        mock_robot_utils['execute_robot_card_play'].assert_not_called()
        self._resume_opening_lead(mock_db_utils, mock_broadcast, mock_context)
        mock_robot_utils['execute_robot_card_play'].assert_called_once()
        call_args = mock_robot_utils['execute_robot_card_play'].call_args
        assert call_args[0][1] == 'East'
        assert call_args[0][0]['gameData']['turn'] == 'East'
    
    def test_robot_card_added_to_current_trick(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test robot card is added to currentTrick"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1D', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats']['North'] = 'user-456'
        room_data['seats']['West'] = 'user-123'
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['execute_robot_card_play'].return_value = '4D'
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        mock_robot_utils['execute_robot_card_play'].assert_not_called()
        self._resume_opening_lead(mock_db_utils, mock_broadcast, mock_context)
        mock_robot_utils['execute_robot_card_play'].assert_called_once()
        saved_room = mock_db_utils.get_table.return_value.put_item.call_args_list[-1][1]['Item']
        trick = saved_room['gameData']['currentTrick']
        assert any(play['seat'] == 'East' and play['card'] == '4D' for play in trick)
        assert '4D' not in saved_room['gameData']['hands']['East']
    
    # ==================== I. WEBSOCKET BROADCASTING ====================
    
    def test_human_bid_broadcast_called(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test broadcast_game_update called with action='bidMade' for human bid"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Verify broadcast_game_update was called
        assert mock_broadcast['broadcast_game_update'].called
        # Check first call (human bid)
        first_call = mock_broadcast['broadcast_game_update'].call_args_list[0]
        assert first_call[1]['action'] == 'bidMade'
    
    def test_human_bid_includes_personalized_caller_ack(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Caller now receives explicit authoritative state rather than relying on route responses."""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(user_id='user-123', bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        updates = mock_broadcast['broadcast_to_connection'].call_args_list
        caller = [entry.args[1] for entry in updates if entry.args[0] == 'conn-user-123']
        assert caller
        assert caller[0]['privateState']['hand'] == room_data['gameData']['hands']['North']
        assert 'hands' not in caller[0]['publicState']
    
    def test_robot_bid_broadcast_action(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Human and robot updates use the same canonical bidMade action."""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = '1S'
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Should have human broadcast + robot broadcast
        calls = mock_broadcast['broadcast_game_update'].call_args_list
        assert len(calls) >= 2
        # Second call should be robot bid
        robot_call = calls[1]
        assert robot_call[1]['action'] == 'bidMade'
    
    def test_robot_bid_broadcast_reaches_human_caller(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Caller must observe persisted robot moves, including its latest revision."""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = 'pass'
        event = mock_event_factory(user_id='user-123', bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        updates = mock_broadcast['broadcast_to_connection'].call_args_list
        assert any(entry.args[0] == 'conn-user-123'
                   and len(entry.args[1]['publicState']['bids']) == 2
                   and entry.args[1]['publicState']['revision'] == 2 for entry in updates)
    
    def test_multiple_robot_bids_broadcast_each(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test broadcast called for each robot bid"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        room_states = [copy.deepcopy(room_data) for _ in range(5)]
        mock_db_utils.find_room_by_id.side_effect = room_states
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['1S', '1NT']
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Should have: human bid + first robot + second robot = 3 broadcasts
        calls = mock_broadcast['broadcast_game_update'].call_args_list
        assert len(calls) == 3
        assert calls[0][1]['action'] == 'bidMade'
        assert calls[1][1]['action'] == 'bidMade'
        assert calls[2][1]['action'] == 'bidMade'
    
    def test_contract_info_in_response(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test declarer/contract info included when contract established"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Check that create_seat_based_response was called
        assert mock_broadcast['create_seat_based_response'].called
        call_args = mock_broadcast['create_seat_based_response'].call_args
        # The game_data should have declarer info
        game_data_arg = call_args[1]['game_data']
        assert 'declarer' in game_data_arg
        assert 'contract' in game_data_arg
    
    def test_all_pass_result_in_response(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test gameResult included when all pass"""
        room_data = copy.deepcopy(base_room_data)
        room_data['gameData']['bids'] = [
            {'seat': 'North', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'East', 'bid': 'pass', 'timestamp': 1234567890123},
            {'seat': 'South', 'bid': 'pass', 'timestamp': 1234567890123}
        ]
        room_data['gameData']['turn'] = 'West'
        room_data['seats'] = {
            'North': 'user-456',
            'East': 'ROBOT_1',
            'South': 'user-789',
            'West': 'user-123'
        }
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='pass')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Check game_data has result info
        call_args = mock_broadcast['create_seat_based_response'].call_args
        game_data_arg = call_args[1]['game_data']
        assert game_data_arg['currentPhase'] == 'completed'
        assert game_data_arg['gameResult'] == 'noWinner'
    
    def test_personalized_response_returned(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test personalized response returned to original caller"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Verify response is from create_seat_based_response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        # Should have the mocked response structure
        assert 'action' in body
    
    # ==================== J. DATABASE REFRESH FOR ROBOTS ====================
    
    def test_find_room_called_before_first_robot(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test find_room_by_id called before first robot turn"""
        room_data = copy.deepcopy(base_room_data)
        mock_db_utils.find_room_by_id.return_value = room_data
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid')]
        mock_robot_utils['execute_robot_bid'].return_value = 'pass'
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        first_robot = mock_robot_utils['execute_robot_bid'].call_args.args[0]
        assert first_robot['revision'] == 1
        assert first_robot['gameData']['bids'][0]['bid'] == '1H'
        assert mock_db_utils.get_table.return_value.put_item.call_count == 2
        # Verify it's called with correct room_id
        for call in mock_db_utils.find_room_by_id.call_args_list:
            assert call[0][0] == 'room-123'
    
    def test_find_room_called_before_each_robot(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test find_room_by_id called before each subsequent robot turn"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        room_data['presence']['West'] = room_data['presence'].pop('South')
        room_states = [copy.deepcopy(room_data) for _ in range(5)]
        mock_db_utils.find_room_by_id.side_effect = room_states
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['pass', 'pass']
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        assert response['statusCode'] == 200
        robots = mock_robot_utils['execute_robot_bid'].call_args_list
        assert [entry.args[0]['revision'] for entry in robots] == [1, 2]
        assert [len(entry.args[0]['gameData']['bids']) for entry in robots] == [1, 2]
        saves = mock_db_utils.get_table.return_value.put_item.call_args_list
        assert len(saves) == 3
        assert all('ConditionExpression' in entry.kwargs for entry in saves)
    
    def test_robots_receive_fresh_game_state(self, handler, mock_event_factory, mock_context, mock_db_utils, base_room_data, mock_robot_utils, mock_broadcast, mock_time):
        """Test each robot receives fresh game state with all previous bids"""
        room_data = copy.deepcopy(base_room_data)
        room_data['seats'] = {
            'North': 'user-123',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'user-456'
        }
        room_data['presence']['West'] = room_data['presence'].pop('South')
        
        # Simulate progressive bid history
        call_tracker = [0]
        def progressive_room_state(*args, **kwargs):
            call_tracker[0] += 1
            state = copy.deepcopy(room_data)
            if call_tracker[0] == 1:
                state['gameData']['bids'] = []
            elif call_tracker[0] == 2:
                # Before first robot
                state['gameData']['bids'] = [
                    {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123}
                ]
            elif call_tracker[0] >= 3:
                # Before second robot
                state['gameData']['bids'] = [
                    {'seat': 'North', 'bid': '1H', 'timestamp': 1234567890123},
                    {'seat': 'East', 'bid': '1S', 'timestamp': 1234567890123}
                ]
            return state
        
        mock_db_utils.find_room_by_id.side_effect = progressive_room_state
        mock_robot_utils['get_robot_turns_sequence'].return_value = [('East', 'bid'), ('South', 'bid')]
        mock_robot_utils['execute_robot_bid'].side_effect = ['1S', '1NT']
        event = mock_event_factory(bid='1H')
        
        response = handler.process_websocket_request(event, mock_context)
        
        # Verify both robots were called
        assert mock_robot_utils['execute_robot_bid'].call_count == 2
        first, second = mock_robot_utils['execute_robot_bid'].call_args_list
        assert [bid['bid'] for bid in first.args[0]['gameData']['bids']] == ['1H']
        assert [bid['bid'] for bid in second.args[0]['gameData']['bids']] == ['1H', '1S']
        assert second.args[0]['revision'] == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
