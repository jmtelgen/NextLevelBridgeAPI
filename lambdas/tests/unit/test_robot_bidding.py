"""
Test script for the robot bridge bidding system.

This script demonstrates the intelligent bidding capabilities of the robot players
using the Fantoni-Nunes system.
"""

from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator
from lambdas.core.bidding.bidding_system import BiddingSystem, BiddingContext
from core.robot.robot_bidder import RobotBidder


def test_hand_evaluation():
    """Test hand evaluation functionality."""
    print("=== Testing Hand Evaluation ===")
    
    evaluator = HandEvaluator()
    
    # Test hands
    test_hands = [
        # Strong balanced hand
        ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
        # 5-card major opening
        ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S'],
        # Weak hand
        ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
        # Preempt hand
        ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', 'AH', 'KH', 'QD', 'JC', 'TC', '9C']
    ]
    
    for i, hand in enumerate(test_hands, 1):
        print(f"\nHand {i}: {hand}")
        analysis = evaluator.evaluate_hand(hand)
        print(f"  HCP: {analysis.hcp}")
        print(f"  Distribution Points: {analysis.distribution_points}")
        print(f"  Total Points: {analysis.total_points}")
        print(f"  Longest Suit: {analysis.longest_suit}{analysis.longest_suit_length}")
        print(f"  Balanced: {analysis.balanced}")
        print(f"  Stoppers: {analysis.stoppers}")


def test_opening_bids():
    """Test opening bid decisions."""
    print("\n\n=== Testing Opening Bids ===")
    
    bidding_system = BiddingSystem()
    
    # Test hands for opening bids
    test_cases = [
        # 1C opening
        (['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'], "1C opening"),
        # 1H opening
        (['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S'], "1H opening"),
        # 1NT opening
        (['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'], "1NT opening"),
        # Pass
        (['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'], "Pass")
    ]
    
    for hand, expected in test_cases:
        context = BiddingContext(
            seat='N',
            vulnerability='None',
            position=1,
            previous_bids=[],
            partner_bids=[],
            opponents_bids=[]
        )
        
        bid = bidding_system.get_opening_bid(hand, context)
        print(f"\nHand: {hand[:5]}...")
        print(f"Expected: {expected}")
        print(f"Actual: {bid or 'Pass'}")


def test_robot_bidding():
    """Test complete robot bidding system."""
    print("\n\n=== Testing Robot Bidding System ===")
    
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
            'dealer': 'N'
        },
        'seats': {
            'N': 'ROBOT_1',
            'E': 'ROBOT_2',
            'S': 'ROBOT_3',
            'W': 'ROBOT_4'
        },
        'vulnerability': 'None'
    }
    
    # Test bidding for each robot
    for seat in ['N', 'E', 'S', 'W']:
        hand = room_data['gameData']['hands'][seat]
        bid = robot_bidder.make_bid(room_data, seat)
        description = robot_bidder.get_hand_strength_description(hand)
        
        print(f"\n{seat} Robot:")
        print(f"  Hand: {hand[:5]}...")
        print(f"  Analysis: {description}")
        print(f"  Bid: {bid}")


def test_response_bidding():
    """Test response bidding."""
    print("\n\n=== Testing Response Bidding ===")
    
    bidding_system = BiddingSystem()
    
    # Test responding to 1C opening
    responder_hand = ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S']
    
    context = BiddingContext(
        seat='E',
        vulnerability='None',
        position=2,
        previous_bids=[{'seat': 'N', 'bid': '1C', 'timestamp': 1234567890}],
        partner_bids=[{'seat': 'N', 'bid': '1C', 'timestamp': 1234567890}],
        opponents_bids=[]
    )
    
    bid = bidding_system.get_response(responder_hand, '1C', context)
    print(f"Responding to 1C with: {responder_hand[:5]}...")
    print(f"Response: {bid or 'Pass'}")


if __name__ == "__main__":
    test_hand_evaluation()
    test_opening_bids()
    test_robot_bidding()
    test_response_bidding()
    print("\n\n=== All Tests Completed ===")
