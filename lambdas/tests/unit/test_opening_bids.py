"""
Test script for Fantoni-Nunes opening bids implementation.

This tests the opening bid logic section by section.
"""

from lambdas.core.bidding.fantoni_nunes_bidding import FantoniNunesBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator


def test_opening_bids():
    """Test all opening bid scenarios."""
    print("=== Testing Fantoni-Nunes Opening Bids ===")
    
    bidding_system = FantoniNunesBidding()
    hand_evaluator = HandEvaluator()
    
    # Test cases for each opening bid
    test_cases = [
        # 1C opening tests
        {
            'hand': ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
            'expected': '1C',
            'description': '15+ balanced hand for 1C'
        },
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7C'],
            'expected': '1C', 
            'description': '14+ with 5+C for 1C'
        },
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S', '6C'],
            'expected': '1C',
            'description': '444-1red for 1C'
        },
        
        # 1D opening tests
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8D', '7D'],
            'expected': '1D',
            'description': '14+ with 5+D for 1D'
        },
        
        # 1H opening tests
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9H', '8H', '7H'],
            'expected': '1H',
            'description': '14+ with 5+H for 1H'
        },
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'AH', 'KH', 'QD', 'JC', 'TC', '9H', '8H', '7H', '6H'],
            'expected': '1H',
            'description': '12+ with 4+S and 5+H for 1H'
        },
        
        # 1S opening tests
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9S', '8S', '7S'],
            'expected': '1S',
            'description': '14+ with 5+S for 1S'
        },
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'AH', 'KH', 'QD', 'JC', 'TC', '9S', '8S', '7S', '6S'],
            'expected': '1S',
            'description': '12+ with 4+H and 5+S for 1S'
        },
        
        # 1NT opening tests
        {
            'hand': ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
            'expected': '1NT',
            'description': '12-14 balanced for 1NT'
        },
        
        # 2C opening tests
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', 'AH', 'KH', 'QD', 'JC', 'TC', '9C'],
            'expected': '2C',
            'description': '10-13 with 5C-4other for 2C'
        },
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', 'AH', 'KH', 'QD', 'JC', 'TC', '9C'],
            'expected': '2C',
            'description': '6+C for 2C'
        },
        
        # 2NT opening tests
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S'],
            'expected': '2NT',
            'description': '21-22 balanced for 2NT'
        },
        
        # 3S preempt tests
        {
            'hand': ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', '2H', '3H', '4D', '5C', '6C', '7C'],
            'expected': '3S',
            'description': 'Preempt with 7+S and low HCP'
        },
        
        # Pass tests
        {
            'hand': ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS'],
            'expected': 'pass',
            'description': 'Weak hand should pass'
        }
    ]
    
    # Run tests
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {case['description']}")
        print(f"  Hand: {case['hand'][:5]}...")
        
        # Create bidding context
        analysis = hand_evaluator.evaluate_hand(case['hand'])
        context = BiddingContext(
            current_seat='N',
            dealer='N',
            vulnerability='None',
            bidding_sequence=[],
            hand_analysis=analysis,
            room_id='test_room'
        )
        
        # Get bid
        bid = bidding_system.make_bid(case['hand'], context)
        
        print(f"  Expected: {case['expected']}, Got: {bid}")
        print(f"  Analysis: HCP={analysis.hcp}, Balanced={analysis.balanced}, Suits={analysis.suit_lengths}")
        
        if bid == case['expected']:
            print("  ✓ PASS")
            passed += 1
        else:
            print("  ✗ FAIL")
            failed += 1
    
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    return passed, failed


if __name__ == "__main__":
    test_opening_bids()
