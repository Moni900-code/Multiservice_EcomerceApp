# schemas.py:  data validation and input/output schema
from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str

#for security: password jeno server e chole na jai tai 
class UserResponse(BaseModel):
    username: str
    email: str
    role: str
    class Config:
        orm_mode = True

class UserLogin(BaseModel):
    email: str
    password: str
