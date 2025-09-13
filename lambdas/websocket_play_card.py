import json
import os
import boto3
import time
from typing import Dict
from botocore.exceptions import ClientError
from base_handler import WebSocketBaseHandler
from lambdas.utils.db_utils import db_utils
from lambdas.utils.websocket_utils import broadcast_to_connection
from lambdas.utils.seat_filtering import create_seat_based_response, broadcast_game_update
from lambdas.utils.robot_utils import is_robot_seat, get_robot_turns_sequence, execute_robot_card_play, get_next_seat

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
        try:
            self.validate_route_key(event, 'playCard')
        except ValueError as e:
            return self.error_response(400, str(e))
        
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
        
        # Find user's seat
        user_seat = None
        for seat, occupant in room_item['seats'].items():
            if occupant == user_id:
                user_seat = seat
                break
        
        if not user_seat:
            return self.error_response(400, 'User not found in room')
        
        # Check if it's the user's turn (turn now stores position, not userId)
        if current_turn != user_seat:
            return self.error_response(400, 'Not your turn to play')
        
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
        seats = ['North', 'East', 'South', 'West']
        current_seat_index = seats.index(user_seat)
        next_seat_index = (current_seat_index + 1) % 4
        next_seat = seats[next_seat_index]
        
        # Store the position (North/South/East/West) in turn, not the userId
        game_data['turn'] = next_seat
        
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
            game_data['turn'] = trick_winner  # trick_winner is already a position (N/S/E/W)
            
            # Check if hand is complete (13 tricks)
            if len(game_data['tricks']) == 13:
                # Hand is complete, determine winner
                game_data['currentPhase'] = 'completed'
                room_item['state'] = 'completed'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Broadcast human move immediately
        self._broadcast_human_move(
            room_id=room_id,
            room_item=room_item,
            user_seat=user_seat,
            card=card,
            game_data=game_data
        )
        
        # Execute robot turns if next player is a robot
        robot_turns = get_robot_turns_sequence(room_item, user_seat)
        for robot_seat, action_type in robot_turns:
            if action_type == 'play':
                robot_card = execute_robot_card_play(room_item, robot_seat)
                if robot_card:
                    # Execute robot card play
                    robot_hand = game_data['hands'][robot_seat]
                    robot_hand.remove(robot_card)
                    game_data['hands'][robot_seat] = robot_hand
                    
                    # Add robot play to current trick
                    robot_play_entry = {
                        'seat': robot_seat,
                        'card': robot_card,
                        'timestamp': int(time.time() * 1000)
                    }
                    game_data['currentTrick'].append(robot_play_entry)
                    
                    # Update turn to next player
                    game_data['turn'] = get_next_seat(robot_seat)
                    
                    # Broadcast this robot move immediately
                    self._broadcast_robot_move(
                        room_id=room_id,
                        room_item=room_item,
                        robot_seat=robot_seat,
                        robot_card=robot_card,
                        game_data=game_data
                    )
                    
                    # Check if trick is complete after robot play
                    if len(game_data['currentTrick']) == 4:
                        # Determine winner of the trick
                        contract = game_data.get('contract')
                        trick_winner = self._determine_trick_winner(game_data['currentTrick'], contract)
                        
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
                        game_data['turn'] = trick_winner
                        
                        # Check if hand is complete (13 tricks)
                        if len(game_data['tricks']) == 13:
                            game_data['currentPhase'] = 'completed'
                            room_item['state'] = 'completed'
        
        # Save room again after robot turns
        room_table.put_item(Item=room_item)
        
        # Convert objects to JSON-serializable format
        game_data_serializable = self._convert_for_json(game_data)
        
        # Determine the correct nextTurn value
        # If trick was completed, nextTurn should be the trick winner
        # If trick is not complete, nextTurn should be the next player in rotation
        if trick_completed and trick_winner:
            next_turn = trick_winner  # trick_winner is already a position (N/S/E/W)
        else:
            next_turn = next_seat  # next_seat is already a position (N/S/E/W)
        
        # Create last action for broadcast
        last_action = {
            'action': 'cardPlayed',
            'play': play_entry,
            'nextTurn': next_turn,
            'trickCompleted': trick_completed
        }
        
        if trick_completed and trick_winner:
            last_action['trickWinner'] = trick_winner
        
        # Create personalized response for the original caller
        personalized_response = create_seat_based_response(
            game_data=game_data,
            room_seats=room_item['seats'],
            user_id=user_id,
            action='cardPlayed',
            message=f'Card {card} played successfully'
        )
        

        
        # Return personalized response to the original caller
        return self.success_response(personalized_response.dict())
    
    def _broadcast_human_move(self, room_id: str, room_item: Dict, user_seat: str, 
                             card: str, game_data: Dict):
        """
        Broadcast a human move to all players in real-time.
        
        Args:
            room_id: The room ID
            room_item: The room data
            user_seat: The human player's seat position
            card: The card played by the human
            game_data: Current game data
        """
        # Create personalized response for each player
        def broadcast_to_user(target_user_id, response):
            # Get connection for this user and send message
            connection = db_utils.get_room_connection(target_user_id)
            if connection:
                broadcast_to_connection(connection, response.dict())
        
        # Broadcast human move to all players
        broadcast_game_update(
            room_id=room_id,
            game_data=game_data,
            room_seats=room_item['seats'],
            action='cardPlayed',
            message=f'{user_seat} played {card}',
            broadcast_function=broadcast_to_user
        )
    
    def _broadcast_robot_move(self, room_id: str, room_item: Dict, robot_seat: str, 
                             robot_card: str, game_data: Dict):
        """
        Broadcast a robot move to all players in real-time.
        
        Args:
            room_id: The room ID
            room_item: The room data
            robot_seat: The robot's seat position
            robot_card: The card played by the robot
            game_data: Current game data
        """
        # Create personalized response for each player
        def broadcast_to_user(target_user_id, response):
            # Get connection for this user and send message
            connection = db_utils.get_room_connection(target_user_id)
            if connection:
                broadcast_to_connection(connection, response.dict())
        
        # Broadcast robot move to all players
        broadcast_game_update(
            room_id=room_id,
            game_data=game_data,
            room_seats=room_item['seats'],
            action='robotCardPlayed',
            message=f'Robot {robot_seat} played {robot_card}',
            broadcast_function=broadcast_to_user
        )
    
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