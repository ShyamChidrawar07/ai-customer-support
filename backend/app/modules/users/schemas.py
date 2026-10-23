from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Literal

UserRole = Literal["customer", "agent", "admin"]

class UserCreate(BaseModel):
    user_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = "customer"

class AdminUserCreate(UserCreate):
    user_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    role: UserRole = Field(
            default="customer",
            pattern=r"^(customer|agent|admin)$",
        )
        
class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: UserRole
    is_active: bool


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)