from pydantic import BaseModel
from typing import Optional

class User(BaseModel):
    userId: str
    username: str
    passwordHash: str
    createdAt: str 