# River Watch Backend - Authentication Models
from pydantic import BaseModel, EmailStr
from typing import List, Optional


class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class VesselAdd(BaseModel):
    mmsi: str
    boat_name: str
    is_primary: bool = False


class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    fleet_name: Optional[str] = None
    vessels: List[dict] = []
    settings: dict = {}
    created_at: Optional[str] = None
    auth_provider: Optional[str] = None
