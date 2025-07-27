from pydantic import BaseModel
from typing import Dict, Any

class Room(BaseModel):
    roomId: str
    ownerId: str
    seats: Dict[str, str]
    state: str
    gameData: Any 