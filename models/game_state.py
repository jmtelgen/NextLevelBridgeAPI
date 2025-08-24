from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class Bid(BaseModel):
    seat: str
    bid: str

class Play(BaseModel):
    seat: str
    card: str

class Trick(BaseModel):
    leader: str
    plays: List[Play]

class GameState(BaseModel):
    currentPhase: str
    turn: str
    bids: List[Bid]
    hands: Dict[str, List[str]]
    tricks: List[Trick]

# New seat-based models for secure API responses
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

class PrivateGameState(BaseModel):
    seat: str
    hand: List[str]  # Only the player's own hand
    validBids: Optional[List[str]] = None   # Valid bids they can make (during bidding phase)
    isMyTurn: bool = False  # Whether it's this player's turn
    isDeclarer: bool = False
    isDummy: bool = False
    partnerSeat: Optional[str] = None

class SeatBasedGameResponse(BaseModel):
    publicState: PublicGameState
    privateState: PrivateGameState
    seat: str
    playerId: str
    action: Optional[str] = None
    message: Optional[str] = None

class BroadcastMessage(BaseModel):
    publicState: PublicGameState
    action: Optional[str] = None
    message: Optional[str] = None
    # Note: privateState (including isMyTurn) is calculated per player during broadcast 