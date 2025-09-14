from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime

@dataclass
class User:
    userId: str
    username: str
    passwordHash: str
    createdAt: str
    
    def to_dict(self):
        return asdict(self)

@dataclass
class Room:
    roomId: str
    ownerId: str
    seats: Dict[str, str]
    state: str
    gameData: Any
    
    def to_dict(self):
        return asdict(self)

@dataclass
class Bid:
    seat: str
    bid: str
    
    def to_dict(self):
        return asdict(self)

@dataclass
class Play:
    seat: str
    card: str
    
    def to_dict(self):
        return asdict(self)

@dataclass
class Trick:
    leader: str
    plays: List[Play]
    
    def to_dict(self):
        return {
            'leader': self.leader,
            'plays': [play.to_dict() for play in self.plays]
        }

@dataclass
class GameState:
    currentPhase: str
    turn: str
    bids: List[Bid]
    hands: Dict[str, List[str]]
    tricks: List[Trick]
    
    def to_dict(self):
        return {
            'currentPhase': self.currentPhase,
            'turn': self.turn,
            'bids': [bid.to_dict() for bid in self.bids],
            'hands': self.hands,
            'tricks': [trick.to_dict() for trick in self.tricks]
        } 