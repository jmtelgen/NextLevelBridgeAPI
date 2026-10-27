from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class Bid(BaseModel):
    seat: str
    bid: str
    timestamp: Optional[int] = None

class Play(BaseModel):
    seat: str
    card: str
    timestamp: Optional[int] = None

class Trick(BaseModel):
    leader: str
    plays: List[Play]
    winner: Optional[str] = None

class PendingAction(BaseModel):
    kind: str
    dueAt: int

class GameState(BaseModel):
    currentPhase: str
    turn: Optional[str] = None
    bids: List[Bid]
    hands: Dict[str, List[str]]
    tricks: List[Trick]

# New seat-based models for secure API responses
class PublicGameState(BaseModel):
    currentPhase: str
    turn: Optional[str] = None
    dealer: str  # Current dealer (North, East, South, West)
    vulnerability: str  # "None", "NS", "EW", "Both"
    bids: List[Bid]
    tricks: List[Trick]
    contract: Optional[str] = None
    declarer: Optional[str] = None
    openingLeader: Optional[str] = None
    currentTrick: Optional[List[Play]] = None
    trickWinner: Optional[str] = None
    dummy: Optional[str] = None  # Dummy seat (North, East, South, West)
    dummyHand: Optional[List[str]] = None  # Dummy's hand (visible to all during play)
    previousTrick: Optional[Trick] = None  # Most recently completed trick
    gameResult: Optional[str] = None
    boardNumber: int = 0
    boardId: Optional[str] = None
    agreements: Optional[Dict[str, Any]] = None
    scoreboard: Optional[Dict[str, Any]] = None
    practiceMode: bool = False
    revision: int = 0
    contractMultiplier: int = 1
    dummyRevealed: bool = False
    handCounts: Dict[str, int] = {}
    result: Optional[Dict[str, Any]] = None
    scores: Dict[str, int] = {"NS": 0, "EW": 0}
    robotPending: bool = False
    completedTrick: Optional[Trick] = None
    pendingAction: Optional[PendingAction] = None
    pacing: Optional[Dict[str, int]] = None
    serverTimeMs: Optional[int] = None
    claim: Optional[Dict[str, Any]] = None
    claimSettlement: Optional[Dict[str, Any]] = None
    eventId: Optional[str] = None

class PrivateGameState(BaseModel):
    seat: str
    hand: List[str]  # Only the player's own hand
    validBids: Optional[List[str]] = None   # Valid bids they can make (during bidding phase)
    isMyTurn: bool = False  # Whether it's this player's turn
    isDeclarer: bool = False
    isDummy: bool = False
    partnerSeat: Optional[str] = None
    legalCards: List[str] = []
    playSeat: Optional[str] = None

class SeatBasedGameResponse(BaseModel):
    publicState: PublicGameState
    privateState: PrivateGameState
    seat: str
    action: Optional[str] = None
    message: Optional[str] = None
    room: Optional[Dict[str, Any]] = None

class BroadcastMessage(BaseModel):
    publicState: PublicGameState
    action: Optional[str] = None
    message: Optional[str] = None
    # Note: privateState (including isMyTurn) is calculated per player during broadcast 