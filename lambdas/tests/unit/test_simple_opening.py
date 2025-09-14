"""
Simple test for opening bids to verify the logic works.
"""

from lambdas.core.bidding.fantoni_nunes_bidding import FantoniNunesBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator


def test_simple_opening_bids():
    """Test basic opening bid scenarios."""
    print("=== Testing Simple Opening Bids ===")
    
    bidding_system = FantoniNunesBidding()
    hand_evaluator = HandEvaluator()
    
    # Test 1: Strong balanced hand (should be 1C)
    hand1 = ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S']
    analysis1 = hand_evaluator.evaluate_hand(hand1)
    print(f"Hand 1: {hand1[:5]}...")
    print(f"  HCP: {analysis1.hcp}, Balanced: {analysis1.balanced}, Suits: {analysis1.suit_lengths}")
    
    context1 = BiddingContext(
        current_seat='N',
        dealer='N', 
        vulnerability='None',
        bidding_sequence=[],
        hand_analysis=analysis1,
        room_id='test_room'
    )
    
    bid1 = bidding_system.make_bid(hand1, context1)
    print(f"  Bid: {bid1}")
    print(f"  Expected: 1C (15+ balanced)")
    print()
    
    # Test 2: 5+ spades (should be 1S)
    hand2 = ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9S', '8S', '7S']
    analysis2 = hand_evaluator.evaluate_hand(hand2)
    print(f"Hand 2: {hand2[:5]}...")
    print(f"  HCP: {analysis2.hcp}, Balanced: {analysis2.balanced}, Suits: {analysis2.suit_lengths}")
    
    context2 = BiddingContext(
        current_seat='N',
        dealer='N',
        vulnerability='None', 
        bidding_sequence=[],
        hand_analysis=analysis2,
        room_id='test_room'
    )
    
    bid2 = bidding_system.make_bid(hand2, context2)
    print(f"  Bid: {bid2}")
    print(f"  Expected: 1S (14+ with 5+S)")
    print()
    
    # Test 3: 7+ spades, low HCP (should be 3S preempt)
    hand3 = ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', '2H', '3H', '4D', '5C', '6C', '7C']
    analysis3 = hand_evaluator.evaluate_hand(hand3)
    print(f"Hand 3: {hand3[:5]}...")
    print(f"  HCP: {analysis3.hcp}, Balanced: {analysis3.balanced}, Suits: {analysis3.suit_lengths}")
    
    context3 = BiddingContext(
        current_seat='N',
        dealer='N',
        vulnerability='None',
        bidding_sequence=[],
        hand_analysis=analysis3,
        room_id='test_room'
    )
    
    bid3 = bidding_system.make_bid(hand3, context3)
    print(f"  Bid: {bid3}")
    print(f"  Expected: 3S (preempt with 7+S, low HCP)")
    print()
    
    # Test 4: Weak hand (should pass)
    hand4 = ['2S', '3H', '4D', '5C', '6S', '7H', '8D', '9C', 'TS', 'JH', 'QD', 'KC', 'AS']
    analysis4 = hand_evaluator.evaluate_hand(hand4)
    print(f"Hand 4: {hand4[:5]}...")
    print(f"  HCP: {analysis4.hcp}, Balanced: {analysis4.balanced}, Suits: {analysis4.suit_lengths}")
    
    context4 = BiddingContext(
        current_seat='N',
        dealer='N',
        vulnerability='None',
        bidding_sequence=[],
        hand_analysis=analysis4,
        room_id='test_room'
    )
    
    bid4 = bidding_system.make_bid(hand4, context4)
    print(f"  Bid: {bid4}")
    print(f"  Expected: pass (weak hand)")


if __name__ == "__main__":
    test_simple_opening_bids()
