"""
Test with a proper 15+ HCP balanced hand for 1C opening.
"""

from lambdas.core.bidding.fantoni_nunes_bidding import FantoniNunesBidding, BiddingContext, Bid
from lambdas.core.hand_evaluation.hand_evaluator import HandEvaluator


def test_15hcp_hand():
    """Test with a 15+ HCP balanced hand."""
    print("=== Testing 15+ HCP Balanced Hand ===")
    
    bidding_system = FantoniNunesBidding()
    hand_evaluator = HandEvaluator()
    
    # Create a 15+ HCP balanced hand
    hand = ['AS', 'KH', 'QD', 'JC', 'TS', '9H', '8D', '7C', '6S', '5H', '4D', '3C', '2S']
    analysis = hand_evaluator.evaluate_hand(hand)
    
    print(f"Hand: {hand}")
    print(f"HCP: {analysis.hcp}")
    print(f"Balanced: {analysis.balanced}")
    print(f"Suit lengths: {analysis.suit_lengths}")
    
    # This hand only has 10 HCP, let me create a proper 15+ HCP hand
    hand_15hcp = ['AS', 'KS', 'QS', 'JS', 'TS', 'AH', 'KH', 'QD', 'JC', 'TC', '9D', '8H', '7S']
    analysis_15hcp = hand_evaluator.evaluate_hand(hand_15hcp)
    
    print(f"\nHand 15+ HCP: {hand_15hcp}")
    print(f"HCP: {analysis_15hcp.hcp}")
    print(f"Balanced: {analysis_15hcp.balanced}")
    print(f"Suit lengths: {analysis_15hcp.suit_lengths}")
    
    context = BiddingContext(
        current_seat='N',
        dealer='N',
        vulnerability='None',
        bidding_sequence=[],
        hand_analysis=analysis_15hcp,
        room_id='test_room'
    )
    
    bid = bidding_system.make_bid(hand_15hcp, context)
    print(f"Bid: {bid}")
    print(f"Expected: 1C (15+ balanced)")


if __name__ == "__main__":
    test_15hcp_hand()
