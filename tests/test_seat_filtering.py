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
        room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
        
        assert get_user_seat(room_seats, 'user-1') == 'N'
        assert get_user_seat(room_seats, 'user-2') == 'E'
        assert get_user_seat(room_seats, 'user-3') == 'S'
        assert get_user_seat(room_seats, 'user-4') == 'W'
        assert get_user_seat(room_seats, 'user-5') is None
    
    def test_create_public_game_state(self):
        """Test creating public game state with filtered data"""
        game_data = {
            'currentPhase': 'playing',
            'turn': 'user-2',
            'dealer': 'N',
            'vulnerability': 'NS',
            'bids': [{'seat': 'N', 'bid': '1H'}, {'seat': 'E', 'bid': 'pass'}],
            'tricks': [],
            'contract': '4H',
            'declarer': 'N',
            'hands': {'N': ['AH', 'KH'], 'E': ['AS', 'KS'], 'S': ['AD', 'KD'], 'W': ['AC', 'KC']},
            'dummy': 'S',
            'dummyHand': ['AD', 'KD', 'QD', 'JD']
        }
        
        room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
        
        public_state = create_public_game_state(game_data, room_seats)
        
        assert isinstance(public_state, PublicGameState)
        assert public_state.currentPhase == 'playing'
        assert public_state.turn == 'user-2'
        assert public_state.dealer == 'N'
        assert public_state.vulnerability == 'NS'
        assert public_state.contract == '4H'
        assert public_state.declarer == 'N'
        assert public_state.dummy == 'S'
        assert public_state.dummyHand == ['AD', 'KD', 'QD', 'JD']
        # Should not contain hands (private data)
        assert not hasattr(public_state, 'hands')
    
    def test_create_private_game_state(self):
        """Test creating private game state for a specific user"""
        game_data = {
            'currentPhase': 'bidding',
            'turn': 'user-2',
            'dealer': 'N',
            'vulnerability': 'NS',
            'bids': [{'seat': 'N', 'bid': '1H'}],
            'tricks': [],
            'hands': {'N': ['AH', 'KH'], 'E': ['AS', 'KS'], 'S': ['AD', 'KD'], 'W': ['AC', 'KC']}
        }
        
        room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
        
        # Test for user-1 (North)
        private_state = create_private_game_state(game_data, room_seats, 'user-1', 'N')
        
        assert isinstance(private_state, PrivateGameState)
        assert private_state.seat == 'N'
        assert private_state.hand == ['AH', 'KH']
        assert private_state.isMyTurn is False  # user-2's turn
        assert private_state.isDeclarer is False
        assert private_state.isDummy is False
        assert private_state.partnerSeat == 'S'
        
        # Test for user-2 (East) - their turn
        private_state = create_private_game_state(game_data, room_seats, 'user-2', 'E')
        
        assert private_state.seat == 'E'
        assert private_state.hand == ['AS', 'KS']
        assert private_state.isMyTurn is True  # user-2's turn
        assert private_state.partnerSeat == 'W'
    
    def test_create_seat_based_response(self):
        """Test creating complete seat-based response"""
        game_data = {
            'currentPhase': 'playing',
            'turn': 'user-1',
            'dealer': 'N',
            'vulnerability': 'NS',
            'bids': [{'seat': 'N', 'bid': '1H'}],
            'tricks': [],
            'contract': '4H',
            'declarer': 'N',
            'hands': {'N': ['AH', 'KH'], 'E': ['AS', 'KS'], 'S': ['AD', 'KD'], 'W': ['AC', 'KC']},
            'dummy': 'S',
            'dummyHand': ['AD', 'KD', 'QD', 'JD']
        }
        
        room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
        
        response = create_seat_based_response(
            game_data=game_data,
            room_seats=room_seats,
            user_id='user-1',
            action='cardPlayed',
            message='Card played successfully'
        )
        
        assert isinstance(response, SeatBasedGameResponse)
        assert response.seat == 'N'
        assert response.playerId == 'user-1'
        assert response.message == 'Card played successfully'
        assert response.action == 'cardPlayed'
        
        # Check public state
        assert response.publicState.currentPhase == 'playing'
        assert response.publicState.turn == 'user-1'
        assert response.publicState.contract == '4H'
        assert response.publicState.dummyHand == ['AD', 'KD', 'QD', 'JD']
        
        # Check private state
        assert response.privateState.seat == 'N'
        assert response.privateState.hand == ['AH', 'KH']
        assert response.privateState.isMyTurn is True
        assert response.privateState.partnerSeat == 'S'
    
    def test_user_not_found_in_room(self):
        """Test error handling when user is not found in room"""
        game_data = {'currentPhase': 'waiting'}
        room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
        
        with pytest.raises(ValueError, match="User user-5 not found in room seats"):
            create_seat_based_response(
                game_data=game_data,
                room_seats=room_seats,
                user_id='user-5'
            )
    
    def test_partner_seat_calculation(self):
        """Test partner seat calculation for Bridge partnerships"""
        game_data = {'currentPhase': 'waiting', 'hands': {}}
        room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
        
        # Test N-S partnership
        private_state_n = create_private_game_state(game_data, room_seats, 'user-1', 'N')
        assert private_state_n.partnerSeat == 'S'
        
        private_state_s = create_private_game_state(game_data, room_seats, 'user-3', 'S')
        assert private_state_s.partnerSeat == 'N'
        
        # Test E-W partnership
        private_state_e = create_private_game_state(game_data, room_seats, 'user-2', 'E')
        assert private_state_e.partnerSeat == 'W'
        
        private_state_w = create_private_game_state(game_data, room_seats, 'user-4', 'W')
        assert private_state_w.partnerSeat == 'E'
