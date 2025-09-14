"""
Test with a proper 15+ HCP balanced hand for 1C opening.
"""

from lambdas.core.bidding.fantoni_nunes_bidding import FantoniNunesBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator


def test_balanced_15hcp():
    """Test with a 15+ HCP balanced hand."""
    print("=== Testing 15+ HCP Balanced Hand ===")
    
    bidding_system = FantoniNunesBidding()
    hand_evaluator = HandEvaluator()
    
    # Create a truly balanced 15+ HCP hand (4333 distribution)
    hand = ['AS', 'KS', 'QS', 'JS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S', '6C']
    analysis = hand_evaluator.evaluate_hand(hand)
    
    print(f"Hand: {hand}")
    print(f"HCP: {analysis.hcp}")
    print(f"Balanced: {analysis.balanced}")
    print(f"Suit lengths: {analysis.suit_lengths}")
    
    context = BiddingContext(
        current_seat='N',
        dealer='N',
        vulnerability='None',
        bidding_sequence=[],
        hand_analysis=analysis,
        room_id='test_room'
    )
    
    bid = bidding_system.make_bid(hand, context)
    print(f"Bid: {bid}")
    print(f"Expected: 1C (15+ balanced)")
    
    # Test the 1C opening logic directly
    print(f"\nDirect 1C test:")
    print(f"  HCP >= 15: {analysis.hcp >= 15}")
    print(f"  Balanced: {analysis.balanced}")
    print(f"  Should open 1C: {analysis.hcp >= 15 and analysis.balanced}")


if __name__ == "__main__":
    test_balanced_15hcp()
