import random
from typing import Dict, List, Optional, Tuple
from lambdas.dds.working_dds_wrapper import DDS, DDSError

def is_robot_seat(occupant: str) -> bool:
    """
    Check if a seat is occupied by a robot
    
    Args:
        occupant: The occupant of the seat (user ID or robot ID)
        
    Returns:
        bool: True if the seat is occupied by a robot
    """
    return bool(occupant) and occupant.startswith('ROBOT_')

def get_robot_id(seat: str) -> str:
    """
    Generate a robot ID for a given seat
    
    Args:
        seat: The seat position ('North', 'East', 'South', 'West')
        
    Returns:
        str: Robot ID (e.g., 'ROBOT_1')
    """
    seat_to_robot = {
        'North': 'ROBOT_1',
        'East': 'ROBOT_2', 
        'South': 'ROBOT_3',
        'West': 'ROBOT_4'
    }
    return seat_to_robot.get(seat, 'ROBOT_1')

def fill_empty_seats_with_robots(seats: Dict[str, str]) -> Dict[str, str]:
    """
    Fill empty seats with robots
    
    Args:
        seats: Current seats dictionary
        
    Returns:
        Dict[str, str]: Updated seats with robots in empty positions
    """
    updated_seats = seats.copy()
    robot_counter = 1
    
    for seat in ['North', 'East', 'South', 'West']:
        if not updated_seats.get(seat):
            updated_seats[seat] = f'ROBOT_{robot_counter}'
            robot_counter += 1
    
    return updated_seats

def get_next_seat(current_seat: str) -> str:
    """
    Get the next seat in clockwise order
    
    Args:
        current_seat: Current seat position
        
    Returns:
        str: Next seat position
    """
    seat_order = ['North', 'East', 'South', 'West']
    current_index = seat_order.index(current_seat)
    next_index = (current_index + 1) % 4
    return seat_order[next_index]

def can_start_game_with_robots(seats: Dict[str, str]) -> bool:
    """
    Check if a game can be started (at least one human player)
    
    Args:
        seats: Current seats dictionary
        
    Returns:
        bool: True if game can be started
    """
    human_players = sum(1 for occupant in seats.values() if occupant and not is_robot_seat(occupant))
    return human_players >= 1

def execute_robot_bid(room_data: Dict, robot_seat: str) -> str:
    """
    Execute a robot bid (currently always passes)
    
    Args:
        room_data: Current room data
        robot_seat: The robot's seat position
        
    Returns:
        str: The bid made by the robot
    """
    # For now, robots always pass
    return 'pass'

def execute_robot_card_play(room_data: Dict, robot_seat: str) -> str:
    """
    Execute a robot card play using DDS SolveBoard analysis for intelligent play.
    
    Enhanced with TypeScript-inspired strategy:
    - Multiple solutions analysis (solutions=3)
    - Target-based analysis for declarer vs defender
    - Best solution selection for optimal robot play
    - Dealer awareness for enhanced analysis
    
    Args:
        room_data: Current room data
        robot_seat: The robot's seat position
        
    Returns:
        str: The card played by the robot
    """
    try:
        # Initialize DDS wrapper
        dds = DDS()
        
        game_data = room_data.get('gameData', {})
        hands = game_data.get('hands', {})
        robot_hand = hands.get(robot_seat, [])
        
        if not robot_hand:
            return None
        
        current_trick = game_data.get('currentTrick', [])
        contract = game_data.get('contract', '1N')
        declarer = game_data.get('declarer', 'North')
        
        # Convert seat names to DDS format
        seat_mapping = {'North': 'N', 'East': 'E', 'South': 'S', 'West': 'W'}
        robot_seat_dds = seat_mapping.get(robot_seat, 'N')
        
        # Determine if robot is declarer or defender
        is_declarer = robot_seat == declarer
        
        # Parse contract to get trump and level
        if len(contract) >= 2:
            try:
                contract_level = int(contract[0])
                trump_strain = contract[1:] if len(contract) > 1 else 'N'
            except ValueError:
                contract_level = 1
                trump_strain = 'N'
        else:
            contract_level = 1
            trump_strain = 'N'
        
        # Get dealer information for enhanced analysis
        dealer = game_data.get('dealer', 'North')
        dealer_dds = seat_mapping.get(dealer, 'N')
        
        # Enhanced target-based analysis (like TypeScript version)
        # For declarer: try to make contract
        # For defender: maximize our tricks
        if is_declarer:
            target_tricks = contract_level + 6  # Contract level + 6 tricks
        else:
            target_tricks = -1  # Maximize our tricks
        
        # Use DDS to choose the best card in any situation
        return _choose_best_card_dds(dds, hands, robot_seat_dds, trump_strain, 
                                   current_trick, robot_hand, is_declarer, target_tricks)
            
    except Exception as e:
        # Fallback to simple play if DDS analysis fails
        print(f"Robot card play DDS analysis failed: {e}")
        return _fallback_card_play(room_data, robot_seat)


def _choose_best_card_dds(dds: DDS, hands: Dict[str, List[str]], robot_seat: str, 
                         trump_strain: str, current_trick: List[Dict], 
                         robot_hand: List[str], is_declarer: bool, 
                         target_tricks: int = -1) -> str:
    """Choose the best card using DDS analysis for any situation (lead, follow, or discard)."""
    try:
        # Get available cards (respecting suit following rules)
        available_cards = _get_available_cards(robot_hand, current_trick)
        
        if not available_cards:
            return robot_hand[0]  # Fallback
        
        # Analyze each available card to see which gives the best outcome
        best_card = available_cards[0]
        best_tricks = -1
        
        for card in available_cards:
            # Create a scenario where we play this card
            new_trick = current_trick + [{'card': card, 'seat': robot_seat}]
            
            # Use SolveBoard to get multiple solutions for this play
            try:
                result = dds.solve_board(
                    trump=trump_strain,
                    first=robot_seat,
                    current_trick=[t['card'] for t in new_trick],
                    hands=hands,
                    target=target_tricks,  # Use target-based analysis
                    solutions=3,  # Get multiple solutions like TypeScript version
                    mode=1,
                    thread_index=0
                )
                
                if result:
                    # For robot play, get the best possible outcome
                    best_solution = max(result, key=lambda x: x[1])
                    total_tricks = best_solution[1]
                    if total_tricks > best_tricks:
                        best_tricks = total_tricks
                        best_card = card
                        
            except Exception:
                continue
        
        return best_card
        
    except Exception:
        # Fallback: use bridge heuristics
        return _fallback_card_choice(robot_hand, current_trick)


def _get_available_cards(robot_hand: List[str], current_trick: List[Dict]) -> List[str]:
    """Get available cards considering suit following rules."""
    if not current_trick:
        # Leading - all cards are available
        return robot_hand
    
    # Must follow suit if possible
    lead_suit = current_trick[0]['card'][0]
    led_suit_cards = [card for card in robot_hand if card[0] == lead_suit]
    
    if led_suit_cards:
        # Must follow suit
        return led_suit_cards
    else:
        # Can discard any card
        return robot_hand


def _fallback_card_choice(robot_hand: List[str], current_trick: List[Dict]) -> str:
    """Fallback card choice using bridge heuristics."""
    if not current_trick:
        # Leading - lead highest of longest suit
        return _lead_highest_of_longest(robot_hand)
    
    # Must follow suit if possible
    lead_suit = current_trick[0]['card'][0]
    led_suit_cards = [card for card in robot_hand if card[0] == lead_suit]
    
    if led_suit_cards:
        # Must follow suit - play highest card
        return max(led_suit_cards, key=lambda x: _get_card_rank(x))
    else:
        # Can discard - discard lowest card (usually safest)
        return min(robot_hand, key=lambda x: _get_card_rank(x))


def _lead_highest_of_longest(robot_hand: List[str]) -> str:
    """Fallback: lead highest card of longest suit."""
    suit_lengths = {}
    for card in robot_hand:
        suit = card[0]
        suit_lengths[suit] = suit_lengths.get(suit, 0) + 1
    
    # Find longest suit
    longest_suit = max(suit_lengths.keys(), key=lambda x: suit_lengths[x])
    
    # Find highest card of longest suit
    longest_suit_cards = [card for card in robot_hand if card[0] == longest_suit]
    return max(longest_suit_cards, key=lambda x: _get_card_rank(x))


def _get_card_rank(card: str) -> int:
    """Get numeric rank of card for comparison."""
    rank_mapping = {
        '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9,
        'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
    }
    return rank_mapping.get(card[1], 0)


def _fallback_card_play(room_data: Dict, robot_seat: str) -> str:
    """Fallback card play when DDS analysis fails."""
    game_data = room_data.get('gameData', {})
    hands = game_data.get('hands', {})
    robot_hand = hands.get(robot_seat, [])
    
    if not robot_hand:
        return None
    
    current_trick = game_data.get('currentTrick', [])
    
    # If leading, play first card
    if not current_trick:
        return robot_hand[0]
    
    # If not leading, must follow suit if possible
    lead_suit = current_trick[0]['card'][0]  # Get suit of first card
    
    # Look for cards of the led suit
    led_suit_cards = [card for card in robot_hand if card[0] == lead_suit]
    
    if led_suit_cards:
        # Must follow suit - play first card of led suit
        return led_suit_cards[0]
    else:
        # Can play any card - play first card
        return robot_hand[0]

def get_robot_turns_sequence(room_data: Dict, current_seat: str) -> List[Tuple[str, str]]:
    """
    Get the sequence of robot turns that should execute immediately
    
    Args:
        room_data: Current room data
        current_seat: Current seat that just played
        
    Returns:
        List[Tuple[str, str]]: List of (seat, action_type) tuples for robot turns
    """
    robot_turns = []
    next_seat = get_next_seat(current_seat)
    seats = room_data.get('seats', {})
    game_data = room_data.get('gameData', {})
    current_phase = game_data.get('currentPhase', 'waiting')
    
    # Check consecutive robot turns
    while is_robot_seat(seats.get(next_seat, '')):
        action_type = 'bid' if current_phase == 'bidding' else 'play'
        robot_turns.append((next_seat, action_type))
        next_seat = get_next_seat(next_seat)
    
    return robot_turns
