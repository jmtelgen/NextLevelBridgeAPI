from pydantic import BaseModel
from typing import Dict, Any

class Room(BaseModel):
    roomId: str
    ownerId: str
    playerName: str
    roomName: str
    isPrivate: bool
    seats: Dict[str, str]
    state: str
    gameData: Any 