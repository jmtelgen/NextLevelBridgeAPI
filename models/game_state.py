from pydantic import BaseModel
from typing import List, Dict, Any

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