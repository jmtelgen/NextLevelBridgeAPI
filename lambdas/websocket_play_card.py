import json
import os
import boto3
import time
from botocore.exceptions import ClientError
from base_handler import WebSocketBaseHandler
from lambdas.utils.db_utils import db_utils
from lambdas.utils.websocket_utils import broadcast_to_connections

SUITS = ['C', 'D', 'H', 'S']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']

class WebSocketPlayCardHandler(WebSocketBaseHandler):
    """
    WebSocket handler for playing a card
    """
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket play card request
        """
        # Validate route key
        self.validate_route_key(event, 'playCard')
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        user_id = data.get('userId')
        room_id = data.get('roomId')
        card = data.get('card')
        
        error = self.validate_required_fields(data, ['userId', 'roomId', 'card'])
        if error:
            return self.error_response(400, error)
        
        # Validate card format (e.g., "AH" for Ace of Hearts)
        if len(card) != 2 or card[0] not in RANKS or card[1] not in SUITS:
            return self.error_response(400, f'Invalid card format. Use format like "AH" (Ace of Hearts). Valid ranks: {", ".join(RANKS)}, Valid suits: {", ".join(SUITS)}')
        
        # Get room table reference once
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Fetch room using db_utils (pass table reference to avoid duplicate logging)
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check if room is in playing phase
        if room_item['state'] != 'playing':
            return self.error_response(400, 'Room is not in playing phase')
        
        # Check if it's the user's turn
        game_data = room_item.get('gameData', {})
        current_turn = game_data.get('turn')
        
        if current_turn != user_id:
            return self.error_response(400, 'Not your turn to play')
        
        # Find user's seat
        user_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == user_id:
                user_seat = seat
                break
        
        if not user_seat:
            return self.error_response(400, 'User not found in room')
        
        # Check if user has the card in their hand
        hands = game_data.get('hands', {})
        user_hand = hands.get(user_seat, [])
        
        if card not in user_hand:
            return self.error_response(400, 'Card not in your hand')
        
        # Check if card follows suit (if not leading)
        current_trick = game_data.get('currentTrick', [])
        if current_trick:
            # Not leading, must follow suit if possible
            lead_suit = current_trick[0]['card'][1]  # Get suit of first card
            played_suit = card[1]
            
            if played_suit != lead_suit:
                # Check if player has cards of the led suit
                has_led_suit = any(c[1] == lead_suit for c in user_hand)
                if has_led_suit:
                    return self.error_response(400, f'Must follow suit. Lead suit is {lead_suit}')
        
        # Remove card from hand
        user_hand.remove(card)
        hands[user_seat] = user_hand
        
        # Add card to current trick
        if 'currentTrick' not in game_data:
            game_data['currentTrick'] = []
        
        play_entry = {
            'seat': user_seat,
            'card': card,
            'timestamp': int(time.time() * 1000)  # Unix timestamp in milliseconds
        }
        
        game_data['currentTrick'].append(play_entry)
        
        # Determine next turn
        seats = ['N', 'E', 'S', 'W']
        current_seat_index = seats.index(user_seat)
        next_seat_index = (current_seat_index + 1) % 4
        next_seat = seats[next_seat_index]
        next_player = room_item['seats'][next_seat]
        
        game_data['turn'] = next_player
        
        # Check if trick is complete (4 cards played)
        trick_completed = False
        trick_winner = None
        if len(game_data['currentTrick']) == 4:
            # Determine winner of the trick
            contract = game_data.get('contract')
            trick_winner = self._determine_trick_winner(game_data['currentTrick'], contract)
            trick_completed = True
            
            # Add trick to completed tricks
            if 'tricks' not in game_data:
                game_data['tricks'] = []
            
            game_data['tricks'].append({
                'cards': game_data['currentTrick'],
                'winner': trick_winner
            })
            
            # Clear current trick
            game_data['currentTrick'] = []
            
            # Set next turn to winner
            game_data['turn'] = room_item['seats'][trick_winner]
            
            # Check if hand is complete (13 tricks)
            if len(game_data['tricks']) == 13:
                # Hand is complete, determine winner
                game_data['currentPhase'] = 'completed'
                room_item['state'] = 'completed'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Convert objects to JSON-serializable format
        game_data_serializable = self._convert_for_json(game_data)
        
        # Determine the correct nextTurn value
        # If trick was completed, nextTurn should be the trick winner
        # If trick is not complete, nextTurn should be the next player in rotation
        if trick_completed and trick_winner:
            next_turn = room_item['seats'][trick_winner]
        else:
            next_turn = next_player
        
        # Get active connections and broadcast update (excluding the user who played the card)
        active_connections = db_utils.get_room_connections_excluding_user(room_item['seats'].values(), room_id, user_id)
        
        broadcast_message = {
            'action': 'cardPlayed',
            'play': play_entry,
            'nextTurn': next_turn,
            'gameData': game_data_serializable,
            'roomState': room_item['state'],
            'updateType': 'cardUpdate',
            'trickCompleted': trick_completed
        }
        
        if trick_completed and trick_winner:
            broadcast_message['trickWinner'] = trick_winner
        
        broadcast_to_connections(active_connections, broadcast_message)
        
        # Return success response (same as broadcast to avoid duplication)
        return self.success_response({
            'action': 'cardPlayed',
            'success': True,
            'play': play_entry,
            'nextTurn': next_turn,
            'gameData': game_data_serializable,
            'roomState': room_item['state'],
            'updateType': 'cardUpdate',
            'trickCompleted': trick_completed,
            'message': f'Card {card} played successfully'
        })
    
    def _determine_trick_winner(self, trick, contract=None):
        """
        Determine the winner of a trick based on Bridge rules
        
        Args:
            trick: List of plays in the current trick
            contract: The contract bid (e.g., '3NT', '4H', '2C') - determines trump suit
            
        Returns:
            str: Seat of the trick winner
        """
        if not trick:
            return None
        
        # Validate trick has exactly 4 cards
        if len(trick) != 4:
            return None
        
        # Determine trump suit from contract
        trump_suit = None
        if contract and not contract.endswith('NT'):
            # Extract suit from contract (e.g., '4H' -> 'H', '2C' -> 'C')
            trump_suit = contract[1:]
        
        # Get the lead suit
        lead_suit = trick[0]['card'][1]
        
        # Find the highest card that can win the trick
        highest_card = None
        highest_rank_value = -1
        highest_is_trump = False
        
        for play in trick:
            card = play['card']
            suit = card[1]
            rank = card[0]
            
            # Validate card format
            if len(card) != 2 or rank not in self.RANKS or suit not in self.SUITS:
                continue  # Skip invalid cards
                
            rank_value = self.RANKS.index(rank)
            
            # Check if this card is trump
            is_trump = (suit == trump_suit)
            
            # Determine if this card can win
            can_win = False
            
            if highest_card is None:
                # First card always can win
                can_win = True
            elif highest_is_trump and is_trump:
                # Both are trump - higher rank wins
                can_win = rank_value > highest_rank_value
            elif highest_is_trump and not is_trump:
                # Current highest is trump, this is not - trump wins
                can_win = False
            elif not highest_is_trump and is_trump:
                # Current highest is not trump, this is trump - trump wins
                can_win = True
            else:
                # Neither is trump - only lead suit can win
                if suit == lead_suit and highest_card['card'][1] == lead_suit:
                    can_win = rank_value > highest_rank_value
                elif suit == lead_suit and highest_card['card'][1] != lead_suit:
                    can_win = True
                else:
                    can_win = False
            
            if can_win:
                highest_card = play
                highest_rank_value = rank_value
                highest_is_trump = is_trump
        
        return highest_card['seat'] if highest_card else trick[0]['seat']

# Create handler instance
handler = WebSocketPlayCardHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 