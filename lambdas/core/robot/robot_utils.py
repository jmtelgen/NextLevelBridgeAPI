"""Robot integration selectors; authoritative game rules own state transitions."""

import logging
from typing import Dict, List, Optional, Tuple

from .fair_play import card, legal_cards, rank

LOG = logging.getLogger(__name__)


def validate_seats_format(seats: Dict[str, str]) -> Dict[str, str]:
    """Validate full position names without changing the caller's mapping."""
    valid_positions = {'North', 'East', 'South', 'West'}
    invalid_positions = set(seats) - valid_positions
    if invalid_positions:
        raise ValueError(
            f"Invalid position names found: {invalid_positions}. "
            "Only 'North', 'East', 'South', 'West' are allowed."
        )
    return seats


def is_robot_seat(occupant: str) -> bool:
    return bool(occupant) and occupant.startswith('ROBOT_')


def get_robot_id(seat: str) -> str:
    return {'North': 'ROBOT_1', 'East': 'ROBOT_2',
            'South': 'ROBOT_3', 'West': 'ROBOT_4'}.get(seat, 'ROBOT_1')


def fill_empty_seats_with_robots(seats: Dict[str, str]) -> Dict[str, str]:
    updated_seats = validate_seats_format(seats).copy()
    robot_counter = 1
    for seat in ['North', 'East', 'South', 'West']:
        if not updated_seats.get(seat):
            updated_seats[seat] = f'ROBOT_{robot_counter}'
            robot_counter += 1
    return updated_seats


def get_next_seat(current_seat: str) -> str:
    seat_order = ['North', 'East', 'South', 'West']
    return seat_order[(seat_order.index(current_seat) + 1) % 4]


def can_start_game_with_robots(seats: Dict[str, str]) -> bool:
    return any(occupant and not is_robot_seat(occupant) for occupant in seats.values())


def execute_robot_bid(room_data: Dict, robot_seat: str) -> str:
    """Return a rule-based SAYC call, validated against the shared auction rules."""
    try:
        validate_seats_format(room_data.get('seats', {}))
        from .robot_bidder import RobotBidder
        return RobotBidder().make_bid(room_data, robot_seat)
    except Exception:
        LOG.exception("robot_bid_degraded seat=%s; passing", robot_seat)
        return 'pass'


def execute_robot_card_play(room_data: Dict, robot_seat: str) -> Optional[str]:
    """Select for the physical hand; declarer is the controller when it is dummy."""
    validate_seats_format(room_data.get('seats', {}))
    from .level_policy import choose_for_room
    return choose_for_room(room_data, robot_seat)


def _get_available_cards(robot_hand: List[str], current_trick: List[Dict]) -> List[str]:
    allowed = set(legal_cards(robot_hand, current_trick))
    return [value for value in robot_hand if card(value) in allowed]


def _get_card_rank(value: str) -> int:
    return rank(value)


def _fallback_card_play(room_data: Dict, robot_seat: str) -> Optional[str]:
    from .fair_play import heuristic, observe
    state = observe(room_data, robot_seat)
    if not state.hand:
        return None
    selected = heuristic(state)
    return next(value for value in room_data['gameData']['hands'][robot_seat] if card(value) == selected)


def get_robot_turns_sequence(room_data: Dict, current_seat: str) -> List[Tuple[str, str]]:
    """Compatibility shim: return only the current actionable robot, never a plan.

    Recompute after every authoritative action: auctions finish, trick winners
    lead, and declarer controls dummy. The runtime must not precompute a sequence.
    """
    from .fair_play import partner
    seats = validate_seats_format(room_data.get('seats', {}))
    game = room_data.get('gameData', {})
    phase = game.get('currentPhase', 'waiting')
    if phase not in ('bidding', 'playing'):
        return []
    seat = game.get('currentPlayer') or game.get('turn')
    if seat not in ('North', 'East', 'South', 'West'):
        # An auction without authoritative turn metadata can advance clockwise;
        # playing cannot (the previous trick may have just been won).
        if phase != 'bidding':
            return []
        seat = get_next_seat(current_seat)
    controller = seat
    declarer = game.get('declarer')
    if phase == 'playing' and declarer and seat == partner(declarer):
        controller = declarer
    return [(seat, 'bid' if phase == 'bidding' else 'play')] if is_robot_seat(seats.get(controller, '')) else []
