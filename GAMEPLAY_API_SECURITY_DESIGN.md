# Gameplay API Security Design: Seat-Based Data Filtering

## Executive Summary

This document outlines a comprehensive redesign of the Bridge gameplay APIs to implement seat-based data filtering. The goal is to ensure that players only receive information relevant to their seat, preventing cheating and improving security while maintaining game integrity.

## Current State Analysis

### Current Data Exposure Issues

Based on the codebase analysis, the current implementation exposes sensitive game data to all players:

1. **Full Hand Information**: All players receive complete hand data for all seats (`hands: Dict[str, List[str]]`)
2. **Complete Game State**: The entire `GameState` object is broadcast to all players
3. **Unfiltered Responses**: WebSocket responses include `gameData` with all game information
4. **No Seat-Based Filtering**: All players see the same data regardless of their seat

### Current Data Structures

```python
# Current GameState model exposes everything
class GameState(BaseModel):
    currentPhase: str
    turn: str
    bids: List[Bid]
    hands: Dict[str, List[str]]  # ALL hands visible to ALL players
    tricks: List[Trick]
```

## Proposed Security Architecture

### 1. Seat-Based Response Models

#### 1.1 Public Game State (Visible to All)
```python
class PublicGameState(BaseModel):
    currentPhase: str
    turn: str
    dealer: str  # Current dealer (N, E, S, W)
    vulnerability: str  # "None", "NS", "EW", "Both"
    bids: List[Bid]
    tricks: List[Trick]
    contract: Optional[str] = None
    declarer: Optional[str] = None
    openingLeader: Optional[str] = None
    currentTrick: Optional[List[Play]] = None
    trickWinner: Optional[str] = None
    dummy: Optional[str] = None  # Dummy seat (N, E, S, W)
    dummyHand: Optional[List[str]] = None  # Dummy's hand (visible to all during play)
    previousTrick: Optional[Trick] = None  # Most recently completed trick
    gameResult: Optional[str] = None
```

#### 1.2 Private Game State (Seat-Specific)
```python
class PrivateGameState(BaseModel):
    seat: str
    hand: List[str]  # Only the player's own hand
    validBids: Optional[List[str]] = None   # Valid bids they can make (during bidding phase)
    isMyTurn: bool = False  # Whether it's this player's turn
    isDeclarer: bool = False
    isDummy: bool = False
    partnerSeat: Optional[str] = None
```

#### 1.3 Seat-Based Response Model
```python
class SeatBasedGameResponse(BaseModel):
    publicState: PublicGameState
    privateState: PrivateGameState
    seat: str
    playerId: str
    lastAction: Optional[Dict[str, Any]] = None
    message: Optional[str] = None

class BroadcastMessage(BaseModel):
    publicState: PublicGameState
    lastAction: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    # Note: privateState (including isMyTurn) is calculated per player during broadcast
```

### 2. Data Filtering Strategy

#### 2.1 Hand Data Filtering
- **Current**: All players see all hands
- **Proposed**: Each player only sees their own hand, plus the dummy hand (if applicable)
- **Implementation**: 
  - Filter `hands` dictionary to only include the player's seat in private state
  - Include dummy hand in public state during play phase
  - Dummy hand is visible to all players in Bridge

#### 2.2 Valid Moves Calculation
- **Current**: Server may provide valid moves
- **Proposed**: Frontend calculates valid moves based on game rules and current state
- **Rationale**: 
  - Avoids duplicating Bridge rule logic on server
  - Prevents potential security exploits through move validation
  - Frontend has all necessary information (hand, current trick, contract)
  - Reduces server complexity and maintenance burden

#### 2.3 Trick Data Filtering
- **Current**: All trick information is public
- **Proposed**: Keep trick data public (cards played are visible to all)
- **Rationale**: In Bridge, played cards are public information

#### 2.4 Dummy Hand Filtering
- **Current**: Dummy hand may not be properly exposed
- **Proposed**: Dummy hand is public information during play phase
- **Rationale**: In Bridge, dummy's hand is exposed and visible to all players

#### 2.5 Game Setup Information
- **Current**: Dealer and vulnerability may not be consistently exposed
- **Proposed**: Dealer and vulnerability are public information
- **Rationale**: These are fundamental Bridge game setup elements known to all players

#### 2.6 Bid Data Filtering
- **Current**: All bid information is public
- **Proposed**: Keep bid data public (bidding is public in Bridge)
- **Rationale**: Bidding information is public knowledge in Bridge

#### 2.7 Turn and Phase Information
- **Current**: All players see current turn
- **Proposed**: All players see current turn (public information)
- **Additional**: Add `isMyTurn` boolean to private state for UI convenience
- **Broadcasting Strategy**: 
  - Calculate `isMyTurn` dynamically for each player's private state during broadcast
  - Include original API caller in broadcast recipients
  - Each player receives personalized response with their specific `isMyTurn` value

### 3. Implementation Plan

#### Phase 1: Model Refactoring
1. Create new seat-based response models
2. Update existing models to support filtering
3. Maintain backward compatibility during transition

#### Phase 2: API Response Filtering
1. Implement seat-based data filtering in all gameplay APIs
2. Update WebSocket broadcast messages with personalized responses
3. Add seat validation and authorization
4. Implement dynamic `isMyTurn` calculation for each broadcast recipient

#### Phase 3: Frontend Integration
1. Update frontend to handle new response format
2. Implement seat-based UI rendering
3. Add security validation on client side

### 4. Detailed API Changes

#### 4.1 WebSocket Play Card API
**Current Response:**
```json
{
  "action": "cardPlayed",
  "success": true,
  "play": {"seat": "N", "card": "AH"},
  "nextTurn": "user-456",
  "gameData": {
    "hands": {
      "N": ["KH", "QH", "JH"],
      "E": ["AS", "KS", "QS"],
      "S": ["AD", "KD", "QD"],
      "W": ["AC", "KC", "QC"]
    },
    "currentTrick": [...],
    "tricks": [...]
  }
}
```

**Proposed Response:**
```json
{
  "action": "cardPlayed",
  "success": true,
  "play": {"seat": "N", "card": "AH"},
  "nextTurn": "user-456",
  "publicState": {
    "currentPhase": "playing",
    "turn": "user-456",
    "dealer": "N",
    "vulnerability": "NS",
    "currentTrick": [...],
    "tricks": [...],
    "dummy": "S",
    "dummyHand": ["AS", "KS", "QS", "JS", "TS", "9S", "8S", "7S", "6S", "5S", "4S", "3S", "2S"],
    "previousTrick": {...},
    "contract": "4H",
    "declarer": "N"
  },
  "privateState": {
    "seat": "N",
    "hand": ["KH", "QH", "JH"],
    "isMyTurn": false
  }
}
```

#### 4.2 WebSocket Make Bid API
**Current Response:**
```json
{
  "action": "bidMade",
  "bid": {"seat": "N", "bid": "1H"},
  "nextTurn": "user-456",
  "gameData": {
    "bids": [...],
    "hands": {...}  // All hands visible
  }
}
```

**Proposed Response:**
```json
{
  "action": "bidMade",
  "bid": {"seat": "N", "bid": "1H"},
  "nextTurn": "user-456",
  "publicState": {
    "currentPhase": "bidding",
    "turn": "user-456",
    "dealer": "N",
    "vulnerability": "NS",
    "bids": [...],
    "contract": null,
    "declarer": null,
    "dummy": null,
    "dummyHand": null,
    "previousTrick": null
  },
  "privateState": {
    "seat": "N",
    "hand": ["AH", "KH", "QH", "JH"],
    "validBids": ["pass", "1D", "1H", "1S", "1NT", "2C"],
    "isMyTurn": false
  }
}
```

### 5. Security Considerations

#### 5.1 Authorization
- Validate that the requesting user is actually in the specified seat
- Ensure seat assignments cannot be manipulated
- Implement proper session validation

#### 5.2 Broadcasting Strategy
- Include original API caller in broadcast recipients
- Calculate `isMyTurn` dynamically for each player's private state
- Ensure each player receives personalized response with correct turn status
- Maintain consistency across all players' game state

#### 5.3 Data Integrity
- Maintain game state consistency across all players
- Ensure public information remains synchronized
- Validate all game moves against current state

#### 5.4 Audit Trail
- Log all data access by seat
- Track suspicious patterns of data requests
- Implement rate limiting per seat

### 6. Broadcasting Implementation Strategy

#### 6.1 Personalized Response Broadcasting
```python
def broadcast_game_update(room_id: str, public_state: PublicGameState, 
                         last_action: Dict, message: str, 
                         exclude_user_id: str = None):
    """
    Broadcast personalized game updates to all players in a room
    """
    # Get all active connections for the room
    connections = get_room_connections(room_id)
    
    for connection in connections:
        user_id = connection['userId']
        seat = get_user_seat(room_id, user_id)
        
        # Skip if this is the excluded user (original caller)
        if exclude_user_id and user_id == exclude_user_id:
            continue
            
        # Calculate personalized data for this player
        is_my_turn = (public_state.turn == user_id)
        private_state = get_private_state_for_seat(room_id, seat, user_id)
        private_state.isMyTurn = is_my_turn  # Set turn status in private state
        
        # Create personalized response
        personalized_response = SeatBasedGameResponse(
            publicState=public_state,
            privateState=private_state,
            seat=seat,
            playerId=user_id,
            lastAction=last_action,
            message=message
        )
        
        # Send to this specific player
        send_to_connection(connection['connectionId'], personalized_response)
```

#### 6.2 Original Caller Response
- The original API caller receives the same personalized response
- `isMyTurn` in private state is calculated based on whether they are the next player
- Ensures consistency between caller and broadcast recipients

#### 6.3 Turn Calculation Logic
```python
def calculate_is_my_turn(current_turn_user_id: str, player_user_id: str) -> bool:
    """Calculate if it's the player's turn"""
    return current_turn_user_id == player_user_id

def get_next_turn_user_id(game_state: GameState, room_seats: Dict) -> str:
    """Determine the next player's turn based on game phase and rules"""
    if game_state.currentPhase == "bidding":
        # Calculate next bidder based on current bidder
        return calculate_next_bidder(game_state, room_seats)
    elif game_state.currentPhase == "playing":
        # Calculate next player based on trick winner or declarer
        return calculate_next_player(game_state, room_seats)
    return None
```

### 7. Migration Strategy

#### 7.1 Backward Compatibility
- Maintain existing API endpoints during transition
- Add new seat-based endpoints alongside current ones
- Use feature flags to control which version is active

#### 7.2 Gradual Rollout
1. Deploy new models and filtering logic
2. Test with a subset of users
3. Gradually migrate frontend to new APIs
4. Remove old endpoints after full migration

#### 7.3 Testing Strategy
- Unit tests for seat-based filtering
- Integration tests for game state consistency
- Security tests for authorization
- Performance tests for filtering overhead
- Broadcast tests for personalized responses

### 8. Performance Impact

#### 8.1 Data Reduction
- **Current**: ~2KB per response (full game state)
- **Proposed**: ~500B per response (filtered state)
- **Benefit**: 75% reduction in data transfer

#### 8.2 Processing Overhead
- Minimal filtering overhead (<1ms)
- Personalized broadcast calculation overhead (~2ms per player)
- Reduced network latency due to smaller payloads
- Improved client-side rendering performance

### 9. Implementation Timeline

#### Week 1-2: Model Development
- Create new seat-based models
- Implement filtering utilities
- Add comprehensive tests

#### Week 3-4: API Updates
- Update WebSocket handlers
- Implement seat-based responses
- Add authorization checks
- Implement personalized broadcasting

#### Week 5-6: Frontend Integration
- Update frontend to handle new responses
- Implement seat-based UI logic
- Add security validation

#### Week 7-8: Testing & Deployment
- Comprehensive testing
- Gradual rollout
- Monitor performance and security

### 10. Risk Mitigation

#### 10.1 Technical Risks
- **Game state inconsistency**: Implement strict validation
- **Performance degradation**: Monitor and optimize filtering
- **Breaking changes**: Maintain backward compatibility
- **Broadcast synchronization**: Ensure all players receive consistent state

#### 10.2 Security Risks
- **Seat spoofing**: Implement proper authorization
- **Data leakage**: Audit all response filtering
- **Timing attacks**: Ensure consistent response times
- **Turn manipulation**: Validate turn calculations and prevent race conditions

### 11. Success Metrics

#### 11.1 Security Metrics
- Zero instances of unauthorized data access
- 100% seat-based data filtering compliance
- Reduced attack surface for cheating

#### 11.2 Performance Metrics
- 75% reduction in response payload size
- <3ms additional processing overhead (including broadcast personalization)
- Improved client-side performance

#### 11.3 User Experience Metrics
- No degradation in game playability
- Maintained real-time responsiveness
- Improved game fairness perception
- Accurate turn indication for all players

## Conclusion

This seat-based data filtering design will significantly improve the security of the Bridge gameplay APIs while maintaining game integrity and user experience. The phased implementation approach ensures a smooth transition with minimal disruption to existing functionality.

The key benefits include:
- **Enhanced Security**: Players can only access their own hand data
- **Improved Performance**: Reduced data transfer and processing
- **Better User Experience**: Cleaner, more focused game state
- **Future-Proof Architecture**: Scalable design for additional security features

This design aligns with Bridge game rules where only played cards and bidding information are public, while hand information remains private to each player.
