import time
from typing import Dict
from lambdas.shared.utils.base_handler import WebSocketBaseHandler
from lambdas.shared.database.db_utils import db_utils
from lambdas.shared.utils.websocket_utils import broadcast_to_connection
from lambdas.shared.utils.seat_filtering import create_seat_based_response, broadcast_game_update
from lambdas.core.robot.robot_utils import is_robot_seat, get_robot_turns_sequence, execute_robot_bid, execute_robot_card_play, get_next_seat

VALID_BIDS = ['pass', '1C', '1D', '1H', '1S', '1NT', '2C', '2D', '2H', '2S', '2NT', 
              '3C', '3D', '3H', '3S', '3NT', '4C', '4D', '4H', '4S', '4NT', 
              '5C', '5D', '5H', '5S', '5NT', '6C', '6D', '6H', '6S', '6NT', 
              '7C', '7D', '7H', '7S', '7NT', 'double', 'redouble']

class WebSocketMakeBidHandler(WebSocketBaseHandler):
    """
    WebSocket handler for making a bid
    """
    
    def _determine_declarer_and_leader(self, bids):
        """
        Determine the declarer and opening leader based on bidding history.
        
        The declarer is the person (on the same team as the one who bid last) 
        who first bid the final contract suit. The opening leader is the player
        to the left of the declarer.
        
        Args:
            bids: List of bid dictionaries with 'seat', 'bid', 'timestamp' keys
            
        Returns:
            tuple: (declarer_seat, opening_leader_seat)
        """
        if not bids:
            return None, None
            
        # Find the final contract (last non-pass bid)
        final_contract = None
        for bid in reversed(bids):
            if bid['bid'] not in ['pass', 'double', 'redouble']:
                final_contract = bid
                break
                
        if not final_contract:
            return None, None
            
        # Extract suit and level from final contract
        contract_bid = final_contract['bid']
        if contract_bid == '1NT' or contract_bid.endswith('NT'):
            suit = 'NT'
        else:
            suit = contract_bid[1:]  # Extract suit (C, D, H, S)
            
        # Find who first bid this suit
        first_suit_bidder = None
        for bid in bids:
            if bid['bid'] not in ['pass', 'double', 'redouble']:
                bid_suit = bid['bid'][1:] if not bid['bid'].endswith('NT') else 'NT'
                if bid_suit == suit:
                    first_suit_bidder = bid['seat']
                    break
                    
        if not first_suit_bidder:
            # This shouldn't happen in normal bidding, but handle gracefully
            return None, None
            
        # Determine if the first suit bidder is on the same team as the final bidder
        final_bidder = final_contract['seat']
        if self._are_partners(first_suit_bidder, final_bidder):
            declarer = first_suit_bidder
        else:
            # If not partners, the declarer is the final bidder
            declarer = final_bidder
            
        # Calculate opening leader (player to the left of declarer)
        seats = ['North', 'East', 'South', 'West']
        declarer_index = seats.index(declarer)
        opening_leader_index = (declarer_index + 1) % 4  # Next clockwise position
        opening_leader = seats[opening_leader_index]
        
        return declarer, opening_leader
    
    def _are_partners(self, seat1, seat2):
        """
        Check if two seats are partners (North/South or East/West).
        
        Args:
            seat1: First seat ('North', 'East', 'South', 'West')
            seat2: Second seat ('North', 'East', 'South', 'West')
            
        Returns:
            bool: True if partners, False otherwise
        """
        return (seat1 in ['North', 'South'] and seat2 in ['North', 'South']) or (seat1 in ['East', 'West'] and seat2 in ['East', 'West'])
    
    def process_websocket_request(self, event, context):
        """
        Process WebSocket make bid request
        """
        # Validate route key
        try:
            self.validate_route_key(event, 'makeBid')
        except ValueError as e:
            return self.error_response(400, str(e))
        
        # Parse request body
        body = self.parse_body(event)
        data = self.extract_data_from_body(body)
        
        # Extract and validate parameters
        user_id = data.get('userId')
        room_id = data.get('roomId')
        bid = data.get('bid')
        
        error = self.validate_required_fields(data, ['userId', 'roomId', 'bid'])
        if error:
            return self.error_response(400, error)
        
        # Validate bid
        if bid not in VALID_BIDS:
            return self.error_response(400, f'Invalid bid. Valid bids: {", ".join(VALID_BIDS)}')
        
        # Get room table reference once
        room_table = db_utils.get_table('ROOM_TABLE')
        
        # Fetch room using db_utils (pass table reference to avoid duplicate logging)
        room_item = db_utils.find_room_by_id(room_id, room_table)
        if not room_item:
            return self.error_response(404, 'Room does not exist')
        
        # Check if room is in bidding phase
        if room_item['state'] != 'bidding':
            return self.error_response(400, 'Room is not in bidding phase')
        
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
            return self.error_response(400, 'Not your turn to bid')
        
        # Add bid to game data
        if 'bids' not in game_data:
            game_data['bids'] = []
        
        bid_entry = {
            'seat': user_seat,
            'bid': bid,
            'timestamp': int(time.time() * 1000)  # Unix timestamp in milliseconds
        }
        
        game_data['bids'].append(bid_entry)
        
        # Determine next turn (simple round-robin)
        seats = ['North', 'East', 'South', 'West']
        current_seat_index = seats.index(user_seat)
        next_seat_index = (current_seat_index + 1) % 4
        next_seat = seats[next_seat_index]
        
        # Store the position (North/South/East/West) in turn, not the userId
        game_data['turn'] = next_seat
        
        # Check if bidding should end (4 passes in a row or valid contract)
        recent_bids = game_data['bids'][-4:] if len(game_data['bids']) >= 4 else game_data['bids']
        if len(recent_bids) >= 4:
            last_four_bids = [b['bid'] for b in recent_bids]
            if last_four_bids == ['pass', 'pass', 'pass', 'pass']:
                # Bidding ended with all passes - game ends with no winner
                game_data['currentPhase'] = 'completed'
                game_data['gameResult'] = 'noWinner'
                game_data['gameEndReason'] = 'allPass'
                game_data['winner'] = None
                # Set next_player to None since game is over
                next_player = None
            elif len([b for b in last_four_bids if b != 'pass']) >= 1:
                # Check if we have a valid contract (3 passes after a non-pass bid)
                non_pass_bids = [b for b in last_four_bids if b != 'pass']
                if len(non_pass_bids) >= 1 and recent_bids[-1]['bid'] == 'pass':
                    # Check if we have 3 consecutive passes after a contract
                    pass_count = 0
                    for bid in reversed(recent_bids):
                        if bid['bid'] == 'pass':
                            pass_count += 1
                        else:
                            break
                    if pass_count >= 3:
                        game_data['currentPhase'] = 'playing'
                        # Find the declarer and set opening leader
                        declarer_seat, opening_leader_seat = self._determine_declarer_and_leader(game_data['bids'])
                        
                        if declarer_seat and opening_leader_seat:
                            # Store the position (N/S/E/W) in turn, not the userId
                            game_data['turn'] = opening_leader_seat
                            # Store declarer and contract information
                            game_data['declarer'] = declarer_seat
                            # Get the final contract bid
                            final_contract_bid = None
                            for bid in reversed(recent_bids):
                                if bid['bid'] not in ['pass', 'double', 'redouble']:
                                    final_contract_bid = bid['bid']
                                    break
                            game_data['contract'] = final_contract_bid
                            game_data['openingLeader'] = opening_leader_seat
                        else:
                            # Fallback to North if something goes wrong
                            game_data['turn'] = 'North'
        
        # Update room state if phase changed
        if game_data['currentPhase'] == 'playing':
            room_item['state'] = 'playing'
        elif game_data['currentPhase'] == 'completed':
            room_item['state'] = 'completed'
        
        # Save updated room
        room_table.put_item(Item=room_item)
        
        # Broadcast human bid immediately (excluding the original caller)
        self._broadcast_human_bid(
            room_id=room_id,
            room_item=room_item,
            user_seat=user_seat,
            bid=bid,
            game_data=game_data,
            exclude_user_id=user_id
        )
        
        # Execute robot turns if next player is a robot
        robot_turns = get_robot_turns_sequence(room_item, user_seat)
        for robot_seat, action_type in robot_turns:
            if action_type == 'bid':
                robot_bid = execute_robot_bid(room_item, robot_seat)
                if robot_bid:
                    # Add robot bid to game data
                    robot_bid_entry = {
                        'seat': robot_seat,
                        'bid': robot_bid,
                        'timestamp': int(time.time() * 1000)
                    }
                    game_data['bids'].append(robot_bid_entry)
                    
                    # Update turn to next player
                    game_data['turn'] = get_next_seat(robot_seat)
                    
                    # Save room data after adding robot bid
                    room_table.put_item(Item=room_item)
                    
                    # Broadcast this robot bid immediately (excluding the original caller)
                    self._broadcast_robot_bid(
                        room_id=room_id,
                        room_item=room_item,
                        robot_seat=robot_seat,
                        robot_bid=robot_bid,
                        game_data=game_data,
                        exclude_user_id=user_id
                    )
                    
                    # Check if bidding should end after robot bid
                    recent_bids = game_data['bids'][-4:] if len(game_data['bids']) >= 4 else game_data['bids']
                    if len(recent_bids) >= 4:
                        last_four_bids = [b['bid'] for b in recent_bids]
                        if last_four_bids == ['pass', 'pass', 'pass', 'pass']:
                            # Bidding ended with all passes
                            game_data['currentPhase'] = 'completed'
                            game_data['gameResult'] = 'noWinner'
                            game_data['gameEndReason'] = 'allPass'
                            game_data['winner'] = None
                        elif len([b for b in last_four_bids if b != 'pass']) >= 1:
                            # Check if we have 3 consecutive passes after a contract
                            non_pass_bids = [b for b in last_four_bids if b != 'pass']
                            if len(non_pass_bids) >= 1 and recent_bids[-1]['bid'] == 'pass':
                                pass_count = 0
                                for bid in reversed(recent_bids):
                                    if bid['bid'] == 'pass':
                                        pass_count += 1
                                    else:
                                        break
                                if pass_count >= 3:
                                    game_data['currentPhase'] = 'playing'
                                    declarer_seat, opening_leader_seat = self._determine_declarer_and_leader(game_data['bids'])
                                    
                                    if declarer_seat and opening_leader_seat:
                                        game_data['turn'] = opening_leader_seat
                                        game_data['declarer'] = declarer_seat
                                        final_contract_bid = None
                                        for bid in reversed(recent_bids):
                                            if bid['bid'] not in ['pass', 'double', 'redouble']:
                                                final_contract_bid = bid['bid']
                                                break
                                        game_data['contract'] = final_contract_bid
                                        game_data['openingLeader'] = opening_leader_seat
                                    else:
                                        game_data['turn'] = 'North'
        
        # Update room state if phase changed
        if game_data['currentPhase'] == 'playing':
            room_item['state'] = 'playing'
            
            # Check if opening leader is a robot and trigger card play
            # Only proceed if openingLeader was actually set during this phase change
            opening_leader = game_data.get('openingLeader')
            if opening_leader:  # Only proceed if openingLeader exists
                opening_leader_occupant = room_item['seats'].get(opening_leader)
                if opening_leader_occupant and is_robot_seat(opening_leader_occupant):
                    # Trigger robot to play opening lead
                    robot_card = execute_robot_card_play(room_item, opening_leader)
                if robot_card:
                    # Execute robot card play
                    robot_hand = game_data['hands'][opening_leader]
                    robot_hand.remove(robot_card)
                    game_data['hands'][opening_leader] = robot_hand
                    
                    # Add robot play to current trick
                    if 'currentTrick' not in game_data:
                        game_data['currentTrick'] = []
                    
                    robot_play_entry = {
                        'seat': opening_leader,
                        'card': robot_card,
                        'timestamp': int(time.time() * 1000)
                    }
                    game_data['currentTrick'].append(robot_play_entry)
                    
                    # Update turn to next player
                    game_data['turn'] = get_next_seat(opening_leader)
                    
                    # Broadcast this robot move immediately
                    self._broadcast_robot_card_play(
                        room_id=room_id,
                        room_item=room_item,
                        robot_seat=opening_leader,
                        robot_card=robot_card,
                        game_data=game_data
                    )
                    
        elif game_data['currentPhase'] == 'completed':
            room_item['state'] = 'completed'
        
        # Save room again after robot turns
        room_table.put_item(Item=room_item)
        
        # Create last action for broadcast
        last_action = {
            'action': 'bidMade',
            'bid': bid_entry,
            'nextTurn': game_data['turn']  # Now stores position (North/South/East/West)
        }
        
        # Add bidding result information if phase changed
        if game_data.get('currentPhase') == 'playing' and 'declarer' in game_data:
            if game_data['declarer'] is None:
                last_action['biddingResult'] = 'allPass'
                message = 'Bidding ended with all passes'
            else:
                last_action['biddingResult'] = 'contract'
                last_action['declarer'] = game_data['declarer']
                last_action['contract'] = game_data['contract']
                last_action['openingLeader'] = game_data['openingLeader']
                message = f'Contract: {game_data["contract"]} by {game_data["declarer"]}'
        elif game_data.get('currentPhase') == 'completed':
            last_action['biddingResult'] = 'allPass'
            last_action['gameResult'] = 'noWinner'
            last_action['gameEndReason'] = 'allPass'
            message = 'Game ended - all players passed'
        else:
            message = f'Bid {bid} recorded successfully'
        
        # Create personalized response for the original caller
        personalized_response = create_seat_based_response(
            game_data=game_data,
            room_seats=room_item['seats'],
            user_id=user_id,
            action='bidMade',
            message=message
        )
        

        
        # Return personalized response to the original caller
        return self.success_response(personalized_response.dict())
    
    def _broadcast_human_bid(self, room_id: str, room_item: Dict, user_seat: str, 
                            bid: str, game_data: Dict, exclude_user_id: str = None):
        """
        Broadcast a human bid to all players in real-time.
        
        Args:
            room_id: The room ID
            room_item: The room data
            user_seat: The human player's seat position
            bid: The bid made by the human
            game_data: Current game data
            exclude_user_id: Optional user ID to exclude from broadcast (usually the original caller)
        """
        # Create personalized response for each player
        def broadcast_to_user(target_user_id, response):
            # Get connection for this user and send message
            connection = db_utils.get_room_connection(target_user_id)
            if connection:
                broadcast_to_connection(connection, response.dict())
        
        # Broadcast human bid to all players (excluding the original caller)
        broadcast_game_update(
            room_id=room_id,
            game_data=game_data,
            room_seats=room_item['seats'],
            action='bidMade',
            message=f'{user_seat} bid {bid}',
            exclude_user_id=exclude_user_id,
            broadcast_function=broadcast_to_user
        )
    
    def _broadcast_robot_bid(self, room_id: str, room_item: Dict, robot_seat: str, 
                            robot_bid: str, game_data: Dict, exclude_user_id: str = None):
        """
        Broadcast a robot bid to all players in real-time.
        
        Args:
            room_id: The room ID
            room_item: The room data
            robot_seat: The robot's seat position
            robot_bid: The bid made by the robot
            game_data: Current game data
            exclude_user_id: Optional user ID to exclude from broadcast (usually the original caller)
        """
        # Create personalized response for each player
        def broadcast_to_user(target_user_id, response):
            # Get connection for this user and send message
            connection = db_utils.get_room_connection(target_user_id)
            if connection:
                broadcast_to_connection(connection, response.dict())
        
        # Broadcast robot bid to all players (excluding the original caller)
        broadcast_game_update(
            room_id=room_id,
            game_data=game_data,
            room_seats=room_item['seats'],
            action='robotBidMade',
            message=f'Robot {robot_seat} bid {robot_bid}',
            exclude_user_id=exclude_user_id,
            broadcast_function=broadcast_to_user
        )
    
    def _broadcast_robot_card_play(self, room_id: str, room_item: Dict, robot_seat: str, 
                                  robot_card: str, game_data: Dict):
        """
        Broadcast a robot card play to all players in real-time.
        
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
        
        # Broadcast robot card play to all players
        broadcast_game_update(
            room_id=room_id,
            game_data=game_data,
            room_seats=room_item['seats'],
            action='robotCardPlayed',
            message=f'Robot {robot_seat} played {robot_card}',
            broadcast_function=broadcast_to_user
        )

# Create handler instance
handler = WebSocketMakeBidHandler()

# Lambda handler function
def lambda_handler(event, context):
    return handler.handle_websocket_request(event, context) 