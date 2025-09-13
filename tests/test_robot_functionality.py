import pytest
import sys
import os

# Add the lambdas directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lambdas'))

from lambdas.utils.robot_utils import (
    is_robot_seat, 
    get_robot_id, 
    fill_empty_seats_with_robots, 
    get_next_seat,
    can_start_game_with_robots,
    execute_robot_bid,
    execute_robot_card_play,
    get_robot_turns_sequence
)

class TestRobotUtils:
    """Test robot utility functions"""
    
    def test_is_robot_seat(self):
        """Test robot seat detection"""
        assert is_robot_seat('ROBOT_1') == True
        assert is_robot_seat('ROBOT_2') == True
        assert is_robot_seat('user123') == False
        assert is_robot_seat('') == False
        assert is_robot_seat(None) == False
    
    def test_get_robot_id(self):
        """Test robot ID generation"""
        assert get_robot_id('North') == 'ROBOT_1'
        assert get_robot_id('East') == 'ROBOT_2'
        assert get_robot_id('South') == 'ROBOT_3'
        assert get_robot_id('West') == 'ROBOT_4'
    
    def test_fill_empty_seats_with_robots(self):
        """Test filling empty seats with robots"""
        # Test with some empty seats
        seats = {
            'North': 'user1',
            'East': '',
            'South': 'user2',
            'West': ''
        }
        
        filled_seats = fill_empty_seats_with_robots(seats)
        
        assert filled_seats['North'] == 'user1'
        assert filled_seats['East'] == 'ROBOT_1'
        assert filled_seats['South'] == 'user2'
        assert filled_seats['West'] == 'ROBOT_2'
        
        # Test with all empty seats
        empty_seats = {
            'North': '',
            'East': '',
            'South': '',
            'West': ''
        }
        
        filled_empty = fill_empty_seats_with_robots(empty_seats)
        assert filled_empty['North'] == 'ROBOT_1'
        assert filled_empty['East'] == 'ROBOT_2'
        assert filled_empty['South'] == 'ROBOT_3'
        assert filled_empty['West'] == 'ROBOT_4'
    
    def test_get_next_seat(self):
        """Test next seat calculation"""
        assert get_next_seat('North') == 'East'
        assert get_next_seat('East') == 'South'
        assert get_next_seat('South') == 'West'
        assert get_next_seat('West') == 'North'
    
    def test_can_start_game_with_robots(self):
        """Test game start validation"""
        # Should be able to start with 1 human
        seats_1_human = {
            'North': 'user1',
            'East': 'ROBOT_1',
            'South': 'ROBOT_2',
            'West': 'ROBOT_3'
        }
        assert can_start_game_with_robots(seats_1_human) == True
        
        # Should be able to start with 2 humans
        seats_2_humans = {
            'North': 'user1',
            'East': 'user2',
            'South': 'ROBOT_1',
            'West': 'ROBOT_2'
        }
        assert can_start_game_with_robots(seats_2_humans) == True
        
        # Should NOT be able to start with 0 humans
        seats_all_robots = {
            'North': 'ROBOT_1',
            'East': 'ROBOT_2',
            'South': 'ROBOT_3',
            'West': 'ROBOT_4'
        }
        assert can_start_game_with_robots(seats_all_robots) == False
    
    def test_execute_robot_bid(self):
        """Test robot bidding (currently always passes)"""
        room_data = {'gameData': {'currentPhase': 'bidding'}}
        assert execute_robot_bid(room_data, 'North') == 'pass'
        assert execute_robot_bid(room_data, 'East') == 'pass'
    
    def test_execute_robot_card_play(self):
        """Test robot card playing"""
        room_data = {
            'gameData': {
                'hands': {
                    'North': ['AS', 'KH', 'QD', 'JC'],
                    'East': ['2S', '3H', '4D', '5C']
                },
                'currentTrick': []
            }
        }
        
        # Test leading (should play first card)
        card = execute_robot_card_play(room_data, 'North')
        assert card == 'AS'
        
        # Test following suit
        room_data['gameData']['currentTrick'] = [{'card': 'KS', 'seat': 'South'}]
        card = execute_robot_card_play(room_data, 'North')
        assert card == 'AS'  # Should play spade since it has one
        
        # Test not following suit (no spades in hand)
        room_data['gameData']['hands']['East'] = ['2H', '3D', '4C', '5H']
        card = execute_robot_card_play(room_data, 'East')
        assert card == '2H'  # Should play first card since no spades
    
    def test_get_robot_turns_sequence(self):
        """Test robot turn sequence detection"""
        room_data = {
            'seats': {
                'North': 'user1',
                'East': 'ROBOT_1',
                'South': 'ROBOT_2',
                'West': 'user2'
            },
            'gameData': {
                'currentPhase': 'bidding'
            }
        }
        
        # After North (user) plays, should get East and South robots
        robot_turns = get_robot_turns_sequence(room_data, 'North')
        assert len(robot_turns) == 2
        assert robot_turns[0] == ('East', 'bid')
        assert robot_turns[1] == ('South', 'bid')
        
        # Test playing phase
        room_data['gameData']['currentPhase'] = 'playing'
        robot_turns = get_robot_turns_sequence(room_data, 'North')
        assert len(robot_turns) == 2
        assert robot_turns[0] == ('East', 'play')
        assert robot_turns[1] == ('South', 'play')
        
        # Test with no consecutive robots
        room_data['seats']['East'] = 'user3'
        robot_turns = get_robot_turns_sequence(room_data, 'North')
        assert len(robot_turns) == 0

if __name__ == '__main__':
    pytest.main([__file__])


