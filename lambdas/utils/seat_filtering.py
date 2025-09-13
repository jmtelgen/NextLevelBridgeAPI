"""
Utility functions for seat-based data filtering in Bridge gameplay APIs.
"""
from typing import Dict, List, Optional, Any
from models.game_state import PublicGameState, PrivateGameState, SeatBasedGameResponse, GameState
from lambdas.utils.db_utils import db_utils


def get_user_seat(room_seats: Dict[str, str], user_id: str) -> Optional[str]:
    """
    Get the seat (N, E, S, W) for a given user ID.
    
    Args:
        room_seats: Dictionary mapping seats to user IDs
        user_id: The user ID to find
        
    Returns:
        The seat (N, E, S, W) or None if user not found
    """
    for seat, occupant in room_seats.items():
        if occupant == user_id:
            return seat
    return None


def convert_seats_to_usernames(seats: Dict[str, str]) -> Dict[str, str]:
    """
    Convert seat mappings from userIds to usernames for privacy
    """
    if not seats:
        return seats
    
    # Get user table reference
    user_table = db_utils.get_table('USER_TABLE')
    
    # Convert each userId to username
    username_seats = {}
    for seat, user_id in seats.items():
        if user_id is None:
            username_seats[seat] = None
        else:
            # Get user info from database
            user_item = db_utils.find_user_by_id(user_id, user_table)
            if user_item:
                username_seats[seat] = user_item.get('username', user_id)  # Fallback to userId if username not found
            else:
                username_seats[seat] = user_id  # Fallback to userId if user not found
    
    return username_seats


def create_public_game_state(game_data: Dict[str, Any], room_seats: Dict[str, str]) -> PublicGameState:
    """
    Create a PublicGameState from game data, filtering out private information.
    
    Args:
        game_data: Raw game data from database
        room_seats: Dictionary mapping seats to user IDs
        
    Returns:
        PublicGameState with only public information
    """
    return PublicGameState(
        currentPhase=game_data.get('currentPhase', 'waiting'),
        turn=game_data.get('turn', ''),
        dealer=game_data.get('dealer', 'North'),
        vulnerability=game_data.get('vulnerability', 'None'),
        bids=game_data.get('bids', []),
        tricks=game_data.get('tricks', []),
        contract=game_data.get('contract'),
        declarer=game_data.get('declarer'),
        openingLeader=game_data.get('openingLeader'),
        currentTrick=game_data.get('currentTrick'),
        trickWinner=game_data.get('trickWinner'),
        dummy=game_data.get('dummy'),
        dummyHand=game_data.get('dummyHand'),
        previousTrick=game_data.get('previousTrick'),
        gameResult=game_data.get('gameResult')
    )


def create_private_game_state(
    game_data: Dict[str, Any], 
    room_seats: Dict[str, str], 
    user_id: str,
    seat: str
) -> PrivateGameState:
    """
    Create a PrivateGameState for a specific user, including only their private information.
    
    Args:
        game_data: Raw game data from database
        room_seats: Dictionary mapping seats to user IDs
        user_id: The user ID for this private state
        seat: The seat (N, E, S, W) for this user
        
    Returns:
        PrivateGameState with only this user's private information
    """
    hands = game_data.get('hands', {})
    user_hand = hands.get(seat, [])
    
    # Calculate if it's this user's turn
    is_my_turn = game_data.get('turn') == seat  # turn now stores position (N/S/E/W), not userId
    
    # Determine if user is declarer or dummy
    declarer_seat = game_data.get('declarer')
    dummy_seat = game_data.get('dummy')
    
    is_declarer = declarer_seat == seat
    is_dummy = dummy_seat == seat
    
    # Calculate partner seat (Bridge partners: North-South, East-West)
    partner_seat = None
    if seat in ['North', 'South']:
        partner_seat = 'South' if seat == 'North' else 'North'
    elif seat in ['East', 'West']:
        partner_seat = 'West' if seat == 'East' else 'East'
    
    # Calculate valid bids during bidding phase
    valid_bids = None
    if game_data.get('currentPhase') == 'bidding' and is_my_turn:
        valid_bids = calculate_valid_bids(game_data)
    
    return PrivateGameState(
        seat=seat,
        hand=user_hand,
        validBids=valid_bids,
        isMyTurn=is_my_turn,
        isDeclarer=is_declarer,
        isDummy=is_dummy,
        partnerSeat=partner_seat
    )


def calculate_valid_bids(game_data: Dict[str, Any]) -> List[str]:
    """
    Calculate valid bids for the current player during bidding phase.
    
    Args:
        game_data: Raw game data from database
        
    Returns:
        List of valid bid strings
    """
    # Basic bid options - in a full implementation, this would be more sophisticated
    basic_bids = ['pass', '1C', '1D', '1H', '1S', '1NT', '2C', '2D', '2H', '2S', '2NT', 
                  '3C', '3D', '3H', '3S', '3NT', '4C', '4D', '4H', '4S', '4NT',
                  '5C', '5D', '5H', '5S', '5NT', '6C', '6D', '6H', '6S', '6NT',
                  '7C', '7D', '7H', '7S', '7NT']
    
    # For now, return all basic bids
    # TODO: Implement proper bid validation based on current bidding state
    return basic_bids


def create_seat_based_response(
    game_data: Dict[str, Any],
    room_seats: Dict[str, str],
    user_id: str,
    action: Optional[str] = None,
    message: Optional[str] = None
) -> SeatBasedGameResponse:
    """
    Create a complete seat-based response for a specific user.
    
    Args:
        game_data: Raw game data from database
        room_seats: Dictionary mapping seats to user IDs
        user_id: The user ID for this response
        last_action: Optional action that triggered this response
        message: Optional message to include
        
    Returns:
        SeatBasedGameResponse with filtered data for this user
    """
    seat = get_user_seat(room_seats, user_id)
    if not seat:
        raise ValueError(f"User {user_id} not found in room seats")
    
    public_state = create_public_game_state(game_data, room_seats)
    private_state = create_private_game_state(game_data, room_seats, user_id, seat)
    
    return SeatBasedGameResponse(
        publicState=public_state,
        privateState=private_state,
        seat=seat,
        action=action,
        message=message
    )


def broadcast_game_update(
    room_id: str,
    game_data: Dict[str, Any],
    room_seats: Dict[str, str],
    action: str,
    message: str,
    exclude_user_id: str = None,
    broadcast_function=None
):
    """
    Broadcast personalized game updates to all players in a room.
    
    Args:
        room_id: The room ID
        game_data: Raw game data from database
        room_seats: Dictionary mapping seats to user IDs
        last_action: The action that triggered this broadcast
        message: Message to include in the broadcast
        exclude_user_id: Optional user ID to exclude from broadcast
        broadcast_function: Function to call for each player's personalized message
    """
    print(f"Broadcasting game update for seats {room_seats}")
    if not broadcast_function:
        return
    
    # Get all active connections for the room
    # This would typically come from a database or connection manager
    # For now, we'll assume we have access to all users in the room
    for _, user_id in room_seats.items():
        print(f"Broadcasting to user {user_id}")
        # Skip if this is the excluded user (original caller)
        if exclude_user_id and user_id == exclude_user_id:
            continue
            
        # Create personalized response for this player
        try:
            print(f"Creating personalized response for user {user_id}")
            personalized_response = create_seat_based_response(
                game_data, room_seats, user_id, action, message
            )
            
            # Send to this specific player
            broadcast_function(user_id, personalized_response)
        except Exception as e:
            # Log error but continue with other players
            print(f"Error creating response for user {user_id}: {e}")
            continue
