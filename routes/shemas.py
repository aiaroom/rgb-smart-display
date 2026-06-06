from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# Auth schemas
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    company_name: str
    password: str
    role: str = "uk_admin"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    company_name: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True

# Ujin
class UjinTokenCreate(BaseModel):
    token_key: str
    token_value: str
    available_buildings: List[int] = []

class UjinTokenResponse(BaseModel):
    id: int
    token_key: str
    available_buildings: List[int]
    is_active: bool

    class Config:
        from_attributes = True

# Display schemas
class DisplayCreate(BaseModel):
    display_id: str
    name: str
    location: Optional[str] = None
    orientation: str = "portrait"

class DisplayResponse(BaseModel):
    id: int
    display_id: str
    name: str
    location: Optional[str]
    orientation: str
    is_active: bool
    last_seen: Optional[datetime]
    emergency_mode: bool
    emergency_text: Optional[str]

    class Config:
        from_attributes = True

class DisplayStatusUpdate(BaseModel):
    is_active: Optional[bool] = None
    last_seen: Optional[datetime] = None

# Template schemas
class WidgetConfig(BaseModel):
    type: str  # clock, weather, news, parking, storage, partners, ads
    position: str  # top, top_left, top_right, center, bottom, bottom_left, bottom_right
    size: str = "medium"  # small, medium, large
    settings: Dict[str, Any] = {}

class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    layout: Dict[str, Any]  # сетка: rows, columns
    widgets: List[WidgetConfig] = []
    theme: str = "dark"
    refresh_interval: int = 30

class TemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    layout: Dict[str, Any]
    widgets: List[WidgetConfig]
    theme: str
    refresh_interval: int
    is_default: bool

    class Config:
        from_attributes = True

# Emergency schemas
class EmergencyActivate(BaseModel):
    display_id: Optional[str] = None  # None = all displays
    message: str
    priority: str = "critical"
    duration_minutes: Optional[int] = 30  # авто-деактивация через N минут

class EmergencyResponse(BaseModel):
    id: int
    display_id: Optional[str]
    message: str
    priority: str
    activated_at: datetime
    activated_by: str

    class Config:
        from_attributes = True