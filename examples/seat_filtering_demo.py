#!/usr/bin/env python3
"""
Demonstration of seat-based data filtering for Bridge gameplay APIs.

This script shows how the new filtering system works by creating
example game states and showing what each player would see.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lambdas.utils.seat_filtering import create_seat_based_response
from models.game_state import PublicGameState, PrivateGameState


def demo_bidding_phase():
    """Demonstrate seat-based filtering during bidding phase"""
    print("=== BIDDING PHASE DEMO ===\n")
    
    # Sample game data during bidding
    game_data = {
        'currentPhase': 'bidding',
        'turn': 'user-2',  # East's turn
        'dealer': 'N',
        'vulnerability': 'NS',
        'bids': [
            {'seat': 'N', 'bid': '1H'},
            {'seat': 'E', 'bid': 'pass'},
            {'seat': 'S', 'bid': '2H'},
            {'seat': 'W', 'bid': 'pass'}
        ],
        'tricks': [],
        'hands': {
            'N': ['AH', 'KH', 'QH', 'JH', 'TH', '9H', '8H', '7H', '6H', '5H', '4H', '3H', '2H'],
            'E': ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', '7S', '6S', '5S', '4S', '3S', '2S'],
            'S': ['AD', 'KD', 'QD', 'JD', 'TD', '9D', '8D', '7D', '6D', '5D', '4D', '3D', '2D'],
            'W': ['AC', 'KC', 'QC', 'JC', 'TC', '9C', '8C', '7C', '6C', '5C', '4C', '3C', '2C']
        }
    }
    
    room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
    
    print("Game State:")
    print(f"  Dealer: {game_data['dealer']}")
    print(f"  Vulnerability: {game_data['vulnerability']}")
    print(f"  Current Turn: {game_data['turn']} (East)")
    bid_strings = [f"{bid['seat']}:{bid['bid']}" for bid in game_data['bids']]
    print(f"  Bids: {bid_strings}")
    print()
    
    # Show what each player sees
    for seat, user_id in room_seats.items():
        print(f"--- {seat} (User: {user_id}) ---")
        
        try:
            response = create_seat_based_response(
                game_data=game_data,
                room_seats=room_seats,
                user_id=user_id,
                last_action={'action': 'bidMade', 'bid': 'pass'},
                message='Bid recorded successfully'
            )
            
            print(f"  Public State:")
            print(f"    Phase: {response.publicState.currentPhase}")
            print(f"    Turn: {response.publicState.turn}")
            print(f"    Dealer: {response.publicState.dealer}")
            print(f"    Vulnerability: {response.publicState.vulnerability}")
            print(f"    Bids: {len(response.publicState.bids)} bids recorded")
            
            print(f"  Private State:")
            print(f"    Seat: {response.privateState.seat}")
            print(f"    Hand: {len(response.privateState.hand)} cards")
            print(f"    Is My Turn: {response.privateState.isMyTurn}")
            print(f"    Partner: {response.privateState.partnerSeat}")
            print(f"    Valid Bids: {response.privateState.validBids is not None}")
            
            # Show hand only for current player (for demo purposes)
            if response.privateState.isMyTurn:
                print(f"    My Hand: {response.privateState.hand}")
            
        except Exception as e:
            print(f"  Error: {e}")
        
        print()


def demo_playing_phase():
    """Demonstrate seat-based filtering during playing phase"""
    print("=== PLAYING PHASE DEMO ===\n")
    
    # Sample game data during playing
    game_data = {
        'currentPhase': 'playing',
        'turn': 'user-1',  # North's turn (declarer)
        'dealer': 'N',
        'vulnerability': 'NS',
        'bids': [
            {'seat': 'N', 'bid': '1H'},
            {'seat': 'E', 'bid': 'pass'},
            {'seat': 'S', 'bid': '2H'},
            {'seat': 'W', 'bid': 'pass'},
            {'seat': 'N', 'bid': '4H'}
        ],
        'tricks': [],
        'contract': '4H',
        'declarer': 'N',
        'openingLeader': 'E',
        'dummy': 'S',
        'dummyHand': ['AD', 'KD', 'QD', 'JD', 'TD', '9D', '8D', '7D', '6D', '5D', '4D', '3D', '2D'],
        'currentTrick': [],
        'hands': {
            'N': ['AH', 'KH', 'QH', 'JH', 'TH', '9H', '8H', '7H', '6H', '5H', '4H', '3H', '2H'],
            'E': ['AS', 'KS', 'QS', 'JS', 'TS', '9S', '8S', '7S', '6S', '5S', '4S', '3S', '2S'],
            'S': ['AD', 'KD', 'QD', 'JD', 'TD', '9D', '8D', '7D', '6D', '5D', '4D', '3D', '2D'],
            'W': ['AC', 'KC', 'QC', 'JC', 'TC', '9C', '8C', '7C', '6C', '5C', '4C', '3C', '2C']
        }
    }
    
    room_seats = {'N': 'user-1', 'E': 'user-2', 'S': 'user-3', 'W': 'user-4'}
    
    print("Game State:")
    print(f"  Contract: {game_data['contract']}")
    print(f"  Declarer: {game_data['declarer']}")
    print(f"  Dummy: {game_data['dummy']}")
    print(f"  Current Turn: {game_data['turn']} (North)")
    print()
    
    # Show what each player sees
    for seat, user_id in room_seats.items():
        print(f"--- {seat} (User: {user_id}) ---")
        
        try:
            response = create_seat_based_response(
                game_data=game_data,
                room_seats=room_seats,
                user_id=user_id,
                last_action={'action': 'cardPlayed', 'card': 'AH'},
                message='Card played successfully'
            )
            
            print(f"  Public State:")
            print(f"    Phase: {response.publicState.currentPhase}")
            print(f"    Turn: {response.publicState.turn}")
            print(f"    Contract: {response.publicState.contract}")
            print(f"    Declarer: {response.publicState.declarer}")
            print(f"    Dummy: {response.publicState.dummy}")
            print(f"    Dummy Hand: {len(response.publicState.dummyHand)} cards visible to all")
            
            print(f"  Private State:")
            print(f"    Seat: {response.privateState.seat}")
            print(f"    Hand: {len(response.privateState.hand)} cards")
            print(f"    Is My Turn: {response.privateState.isMyTurn}")
            print(f"    Is Declarer: {response.privateState.isDeclarer}")
            print(f"    Is Dummy: {response.privateState.isDummy}")
            print(f"    Partner: {response.privateState.partnerSeat}")
            
            # Show hand only for current player (for demo purposes)
            if response.privateState.isMyTurn:
                print(f"    My Hand: {response.privateState.hand}")
            
        except Exception as e:
            print(f"  Error: {e}")
        
        print()


def main():
    """Run the demonstration"""
    print("BRIDGE GAMEPLAY API - SEAT-BASED DATA FILTERING DEMO")
    print("=" * 60)
    print()
    
    demo_bidding_phase()
    print("\n" + "=" * 60 + "\n")
    demo_playing_phase()
    
    print("=== KEY SECURITY FEATURES ===")
    print("✅ Each player only sees their own hand")
    print("✅ Dummy hand is visible to all players during play")
    print("✅ Public information (bids, tricks, contract) visible to all")
    print("✅ Turn status calculated dynamically for each player")
    print("✅ Partner seat automatically calculated")
    print("✅ No sensitive game data leaked between players")


if __name__ == "__main__":
    main()
