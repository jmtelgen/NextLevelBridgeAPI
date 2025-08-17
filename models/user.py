from pydantic import BaseModel

class User(BaseModel):
    userId: str
    username: str
    email: str
    passwordHash: str
    salt: str  # Required salt for enhanced security
    createdAt: str 