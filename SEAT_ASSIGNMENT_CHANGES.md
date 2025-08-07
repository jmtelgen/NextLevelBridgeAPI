# Seat Assignment Changes - Robot Replacement System

## Overview

This document describes the changes made to implement the new seat assignment system where:
1. When a room is created, the creator gets a random seat and the remaining seats are filled with robots
2. When a player joins a room, they can replace a random robot seat
3. The game can start immediately since all seats are always filled

## Changes Made

### 1. Room Creation (`lambdas/room_create.py`)

**Before:**
- Created room with 4 empty seats
- Randomly assigned owner to one seat
- Left 3 seats empty

**After:**
- Creates room with 4 empty seats
- Randomly assigns owner to one seat
- **Immediately fills remaining empty seats with robots**
- Robot IDs follow pattern: `robot-{seat}` (e.g., `robot-N`, `robot-E`, `robot-S`, `robot-W`)

**Key Changes:**
```python
# Fill remaining empty seats with robots
for seat in ['N', 'E', 'S', 'W']:
    if not seats[seat]:
        seats[seat] = f'robot-{seat}'
```

### 2. Room Joining (`lambdas/room_join.py`)

**Before:**
- Only allowed joining empty seats
- Returned error if no empty seats available

**After:**
- Allows joining empty seats OR replacing robot seats
- When no specific seat requested, randomly selects from available seats (empty or robot-occupied)
- When specific seat requested, allows if seat is empty or occupied by robot
- **Replaces robot with human player**

**Key Changes:**
```python
# Find available seats (empty or occupied by robots)
available_seats = []
for seat, occupant in room_item['seats'].items():
    if not occupant or occupant.startswith('robot-'):
        available_seats.append(seat)

# Check if requested seat is available (empty or occupied by robot)
current_occupant = room_item['seats'][requested_seat]
if current_occupant and not current_occupant.startswith('robot-'):
    return {'statusCode': 400, 'body': json.dumps({'error': 'Seat not available'})}
```

### 3. Room Starting (`lambdas/room_start.py`)

**Before:**
- Filled empty seats with robots when game started
- Changed state to 'bidding'

**After:**
- **No longer fills seats with robots** (already done during room creation)
- Only changes state to 'bidding'

**Key Changes:**
```python
# All seats should already be filled (either with humans or robots)
# Just change the state to start the game
room_item['state'] = 'bidding'
```

### 4. WebSocket Room Start (`lambdas/websocket_start_room.py`)

**Before:**
- Filled empty seats with robots when game started

**After:**
- **No longer fills seats with robots** (already done during room creation)
- Only changes state to 'bidding'

## Robot Identification

Robots are identified by the prefix `robot-` followed by their seat position:
- `robot-N` - Robot in North seat
- `robot-E` - Robot in East seat  
- `robot-S` - Robot in South seat
- `robot-W` - Robot in West seat

## Seat Availability Logic

A seat is considered "available" if:
1. It's empty (`''`)
2. It's occupied by a robot (`starts with 'robot-'`)

A seat is considered "unavailable" if:
1. It's occupied by a human player (any ID that doesn't start with `robot-`)

## Test Coverage

Updated tests to cover:
- Room creation with immediate robot filling
- Robot replacement during room joining
- Specific seat selection (empty or robot-occupied)
- Backward compatibility with empty seats
- Proper robot naming convention validation

## Benefits

1. **Immediate Game Readiness**: Rooms are always ready to start since all seats are filled
2. **Flexible Joining**: Players can join at any time by replacing robots
3. **Random Assignment**: When no specific seat is requested, a random robot is replaced
4. **Backward Compatibility**: Still works with rooms that might have empty seats
5. **Clear Robot Identification**: Easy to distinguish robots from human players

## Migration Notes

- Existing rooms with empty seats will still work (backward compatibility maintained)
- New rooms will always have robots in empty seats
- Robot replacement is seamless and doesn't affect game state
- No changes needed to game logic since robots are treated as regular players

## Pydantic Version

The codebase uses **Pydantic v1.10.13** as specified in `requirements.txt`. All model serialization uses the `.dict()` method which is the correct syntax for Pydantic v1.
