"""
Test script for the advanced robot bridge bidding system.

This script demonstrates the full Fantoni-Nunes system implementation
with DDS integration and comprehensive bidding analysis.
"""

from core.robot.robot_bidder import RobotBidder
from lambdas.core.bidding.advanced_bidding_engine import AdvancedBiddingEngine
import os


def test_advanced_hand_evaluation():
    """Test advanced hand evaluation capabilities."""
    print("=== Testing Advanced Hand Evaluation ===")
    
    robot_bidder = RobotBidder()
    
    # Test hands with different characteristics
    test_hands = [
        # Strong balanced hand for 1C opening
        ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
        # 5-card major opening
        ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S'],
        # 1NT opening
        ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
        # Preempt hand
        ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', 'AH', 'KH', 'QD', 'JC', 'TC', '9C']
    ]
    
    for i, hand in enumerate(test_hands, 1):
        print(f"\nHand {i}: {hand[:5]}...")
        analysis = robot_bidder.get_advanced_hand_analysis(hand)
        print(f"  HCP: {analysis['hcp']}")
        print(f"  Distribution Points: {analysis['distribution_points']}")
        print(f"  Total Points: {analysis['total_points']}")
        print(f"  Longest Suit: {analysis['longest_suit']}{analysis['longest_suit_length']}")
        print(f"  Balanced: {analysis['balanced']}")
        print(f"  Stoppers: {analysis['stoppers']}")
        print(f"  Controls: {analysis['controls']}")


def test_advanced_bidding():
    """Test advanced bidding system."""
    print("\n\n=== Testing Advanced Bidding System ===")
    
    robot_bidder = RobotBidder()
    
    # Mock room data
    room_data = {
        'gameData': {
            'hands': {
                'N': ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
                'E': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
                'S': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S'],
                'W': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS']
            },
            'bids': [],
            'dealer': 'N',
            'currentPhase': 'bidding'
        },
        'seats': {
            'N': 'ROBOT_1',
            'E': 'ROBOT_2',
            'S': 'ROBOT_3',
            'W': 'ROBOT_4'
        },
        'vulnerability': 'None',
        'roomId': 'test_room'
    }
    
    # Test bidding for each robot
    for seat in ['N', 'E', 'S', 'W']:
        hand = room_data['gameData']['hands'][seat]
        bid = robot_bidder.make_bid(room_data, seat)
        analysis = robot_bidder.get_advanced_hand_analysis(hand)
        
        print(f"\n{seat} Robot:")
        print(f"  Hand: {hand[:5]}...")
        print(f"  Analysis: {analysis['description']}")
        print(f"  Bid: {bid}")
        
        # Show available bids
        available_bids = robot_bidder.get_available_bids(hand, room_data, seat)
        print(f"  Available bids: {[(b['bid'], f"{b['confidence']:.2f}") for b in available_bids[:3]]}")


def test_algorithm_parser():
    """Test the algorithm parser."""
    print("\n\n=== Testing Algorithm Parser ===")
    
    algorithm_file = os.path.join('dds', 'bridge_bidding_alg.txt')
    
    if os.path.exists(algorithm_file):
        try:
            engine = AdvancedBiddingEngine(algorithm_file)
            print("✓ Algorithm parser initialized successfully")
            
            # Test opening rules
            opening_rules = engine.parser.get_opening_rules()
            print(f"✓ Parsed {len(opening_rules)} opening bid types")
            
            for bid, rules in list(opening_rules.items())[:5]:
                print(f"  {bid}: {len(rules)} rule(s)")
                if rules:
                    print(f"    - {rules[0].description}")
            
        except Exception as e:
            print(f"✗ Algorithm parser failed: {e}")
    else:
        print(f"✗ Algorithm file not found: {algorithm_file}")


def test_algorithm_accuracy():
    """Test algorithm rule accuracy."""
    print("\n\n=== Testing Algorithm Rule Accuracy ===")
    
    robot_bidder = RobotBidder()
    
    # Test specific hands against expected bids
    test_cases = [
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S'],
            'expected_bid': '1S',  # 5+ spades, 14+ HCP
            'description': 'Strong 5-card spade suit'
        },
        {
            'hand': ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
            'expected_bid': 'pass',  # Not strong enough for any opening
            'description': 'Weak balanced hand'
        },
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', '2H', '3H', '4D', '5C', '6C', '7C'],
            'expected_bid': '3S',  # Preempt with 7+ spades, low HCP
            'description': 'Preempt hand'
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        room_data = {
            'gameData': {
                'hands': {'N': case['hand']},
                'bids': [],
                'dealer': 'N',
                'currentPhase': 'bidding'
            },
            'seats': {'N': 'ROBOT_1'},
            'vulnerability': 'None',
            'roomId': 'test_room'
        }
        
        bid = robot_bidder.make_bid(room_data, 'N')
        analysis = robot_bidder.get_advanced_hand_analysis(case['hand'])
        
        print(f"\nTest Case {i}: {case['description']}")
        print(f"  Hand: {case['hand'][:5]}...")
        print(f"  Expected: {case['expected_bid']}, Got: {bid}")
        print(f"  Analysis: {analysis['description']}")
        
        if bid == case['expected_bid']:
            print("  ✓ PASS")
        else:
            print("  ✗ FAIL")


def test_competitive_bidding():
    """Test competitive bidding scenarios."""
    print("\n\n=== Testing Competitive Bidding ===")
    
    robot_bidder = RobotBidder()
    
    # Scenario: Opponents have bid, robot needs to compete
    room_data = {
        'gameData': {
            'hands': {
                'N': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S'],
                'E': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
                'S': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
                'W': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS']
            },
            'bids': [
                {'seat': 'E', 'bid': '1H', 'timestamp': 1234567890},
                {'seat': 'S', 'bid': 'pass', 'timestamp': 1234567891}
            ],
            'dealer': 'E',
            'currentPhase': 'bidding'
        },
        'seats': {
            'N': 'ROBOT_1',
            'E': 'HUMAN_1',
            'S': 'HUMAN_2',
            'W': 'ROBOT_2'
        },
        'vulnerability': 'None',
        'roomId': 'test_room'
    }
    
    # Test West robot's response to 1H opening
    west_hand = room_data['gameData']['hands']['W']
    west_bid = robot_bidder.make_bid(room_data, 'W')
    west_analysis = robot_bidder.get_advanced_hand_analysis(west_hand)
    
    print(f"West Robot (responding to 1H):")
    print(f"  Hand: {west_hand[:5]}...")
    print(f"  Analysis: {west_analysis['description']}")
    print(f"  Bid: {west_bid}")
    
    # Show available bids
    available_bids = robot_bidder.get_available_bids(west_hand, room_data, 'W')
    print(f"  Available bids: {[(b['bid'], f"{b['confidence']:.2f}") for b in available_bids[:5]]}")


def test_slam_bidding():
    """Test slam bidding scenarios."""
    print("\n\n=== Testing Slam Bidding ===")
    
    robot_bidder = RobotBidder()
    
    # Strong hand for slam investigation
    strong_hand = ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S']
    
    room_data = {
        'gameData': {
            'hands': {
                'N': strong_hand,
                'E': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
                'S': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
                'W': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS']
            },
            'bids': [],
            'dealer': 'N',
            'currentPhase': 'bidding'
        },
        'seats': {
            'N': 'ROBOT_1',
            'E': 'ROBOT_2',
            'S': 'ROBOT_3',
            'W': 'ROBOT_4'
        },
        'vulnerability': 'None',
        'roomId': 'test_room'
    }
    
    # Test North robot's opening with strong hand
    north_bid = robot_bidder.make_bid(room_data, 'N')
    north_analysis = robot_bidder.get_advanced_hand_analysis(strong_hand)
    
    print(f"North Robot (strong hand):")
    print(f"  Hand: {strong_hand[:5]}...")
    print(f"  Analysis: {north_analysis['description']}")
    print(f"  Bid: {north_bid}")
    
    # Show available bids
    available_bids = robot_bidder.get_available_bids(strong_hand, room_data, 'N')
    print(f"  Available bids: {[(b['bid'], f"{b['confidence']:.2f}") for b in available_bids[:5]]}")


if __name__ == "__main__":
    test_advanced_hand_evaluation()
    test_advanced_bidding()
    test_algorithm_parser()
    test_algorithm_accuracy()
    test_competitive_bidding()
    test_slam_bidding()
    print("\n\n=== All Advanced Tests Completed ===")
