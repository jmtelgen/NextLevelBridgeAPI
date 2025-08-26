import pytest
from lambdas.utils.seat_filtering import (
    get_user_seat,
    create_public_game_state,
    create_private_game_state,
    create_seat_based_response
)
from models.game_state import PublicGameState, PrivateGameState, SeatBasedGameResponse


class TestSeatFiltering:
    
    def test_get_user_seat(self):
        """Test getting user seat from room seats dictionary"""
        room_seats = {'North': 'user-1', 'East': 'user-2', 'South': 'user-3', 'West': 'user-4'}
        
        assert get_user_seat(room_seats, 'user-1') == 'North'
        assert get_user_seat(room_seats, 'user-2') == 'East'
        assert get_user_seat(room_seats, 'user-3') == 'South'
        assert get_user_seat(room_seats, 'user-4') == 'West'
        assert get_user_seat(room_seats, 'user-5') is None
    
    def test_create_public_game_state(self):
        """Test creating public game state with filtered data"""
        game_data = {
            'currentPhase': 'playing',
            'turn': 'East',  # East's turn (position, not userId)
            'dealer': 'North',
            'vulnerability': 'NS',
            'bids': [{'seat': 'North', 'bid': '1H'}, {'seat': 'East', 'bid': 'pass'}],
            'tricks': [],
            'contract': '4H',
            'declarer': 'North',
            'hands': {'North': ['AH', 'KH'], 'East': ['AS', 'KS'], 'South': ['AD', 'KD'], 'West': ['AC', 'KC']},
            'dummy': 'South',
            'dummyHand': ['AD', 'KD', 'QD', 'JD']
        }
        
        room_seats = {'North': 'user-1', 'East': 'user-2', 'South': 'user-3', 'West': 'user-4'}
        
        public_state = create_public_game_state(game_data, room_seats)
        
        assert isinstance(public_state, PublicGameState)
        assert public_state.currentPhase == 'playing'
        assert public_state.turn == 'East'  # Now stores position, not userId
        assert public_state.dealer == 'North'
        assert public_state.vulnerability == 'NS'
        assert public_state.contract == '4H'
        assert public_state.declarer == 'North'
        assert public_state.dummy == 'South'
        assert public_state.dummyHand == ['AD', 'KD', 'QD', 'JD']
        # Should not contain hands (private data)
        assert not hasattr(public_state, 'hands')
    
    def test_create_private_game_state(self):
        """Test creating private game state for a specific user"""
        game_data = {
            'currentPhase': 'bidding',
            'turn': 'East',  # East's turn (position, not userId)
            'dealer': 'North',
            'vulnerability': 'NS',
            'bids': [{'seat': 'North', 'bid': '1H'}],
            'tricks': [],
            'hands': {'North': ['AH', 'KH'], 'East': ['AS', 'KS'], 'South': ['AD', 'KD'], 'West': ['AC', 'KC']}
        }
        
        room_seats = {'North': 'user-1', 'East': 'user-2', 'South': 'user-3', 'West': 'user-4'}
        
        # Test for user-1 (North)
        private_state = create_private_game_state(game_data, room_seats, 'user-1', 'North')
        
        assert isinstance(private_state, PrivateGameState)
        assert private_state.seat == 'North'
        assert private_state.hand == ['AH', 'KH']
        assert private_state.isMyTurn is False  # East's turn
        assert private_state.isDeclarer is False
        assert private_state.isDummy is False
        assert private_state.partnerSeat == 'South'
        
        # Test for user-2 (East) - their turn
        private_state = create_private_game_state(game_data, room_seats, 'user-2', 'East')
        
        assert private_state.seat == 'East'
        assert private_state.hand == ['AS', 'KS']
        assert private_state.isMyTurn is True  # East's turn
        assert private_state.partnerSeat == 'West'
    
    def test_create_seat_based_response(self):
        """Test creating complete seat-based response"""
        game_data = {
            'currentPhase': 'playing',
            'turn': 'North',  # North's turn (position, not userId)
            'dealer': 'North',
            'vulnerability': 'NS',
            'bids': [{'seat': 'North', 'bid': '1H'}],
            'tricks': [],
            'contract': '4H',
            'declarer': 'North',
            'hands': {'North': ['AH', 'KH'], 'East': ['AS', 'KS'], 'South': ['AD', 'KD'], 'West': ['AC', 'KC']},
            'dummy': 'South',
            'dummyHand': ['AD', 'KD', 'QD', 'JD']
        }
        
        room_seats = {'North': 'user-1', 'East': 'user-2', 'South': 'user-3', 'West': 'user-4'}
        
        response = create_seat_based_response(
            game_data=game_data,
            room_seats=room_seats,
            user_id='user-1',
            action='cardPlayed',
            message='Card played successfully'
        )
        
        assert isinstance(response, SeatBasedGameResponse)
        assert response.seat == 'North'
        assert response.message == 'Card played successfully'
        assert response.action == 'cardPlayed'
        
        # Check public state
        assert response.publicState.currentPhase == 'playing'
        assert response.publicState.turn == 'North'  # Now stores position, not userId
        assert response.publicState.contract == '4H'
        assert response.publicState.dummyHand == ['AD', 'KD', 'QD', 'JD']
        
        # Check private state
        assert response.privateState.seat == 'North'
        assert response.privateState.hand == ['AH', 'KH']
        assert response.privateState.isMyTurn is True
        assert response.privateState.partnerSeat == 'South'
    
    def test_user_not_found_in_room(self):
        """Test error handling when user is not found in room"""
        game_data = {'currentPhase': 'waiting'}
        room_seats = {'North': 'user-1', 'East': 'user-2', 'South': 'user-3', 'West': 'user-4'}
        
        with pytest.raises(ValueError, match="User user-5 not found in room seats"):
            create_seat_based_response(
                game_data=game_data,
                room_seats=room_seats,
                user_id='user-5'
            )
    
    def test_partner_seat_calculation(self):
        """Test partner seat calculation for Bridge partnerships"""
        game_data = {'currentPhase': 'waiting', 'hands': {}}
        room_seats = {'North': 'user-1', 'East': 'user-2', 'South': 'user-3', 'West': 'user-4'}
        
        # Test North-South partnership
        private_state_n = create_private_game_state(game_data, room_seats, 'user-1', 'North')
        assert private_state_n.partnerSeat == 'South'
        
        private_state_s = create_private_game_state(game_data, room_seats, 'user-3', 'South')
        assert private_state_s.partnerSeat == 'North'
        
        # Test East-West partnership
        private_state_e = create_private_game_state(game_data, room_seats, 'user-2', 'East')
        assert private_state_e.partnerSeat == 'West'
        
        private_state_w = create_private_game_state(game_data, room_seats, 'user-4', 'West')
        assert private_state_w.partnerSeat == 'East'
