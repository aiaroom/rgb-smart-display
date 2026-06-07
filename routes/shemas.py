from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TargetType(str, Enum):
    display = "display"
    group = "group"
    complex = "complex"


class UserRole(str, Enum):
    uk_admin = "uk_admin"
    dispatcher = "dispatcher"
    concierge = "concierge"


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    company_name: Optional[str] = None
    password: str = Field(min_length=6)
    role: UserRole = UserRole.uk_admin
    complex_id: Optional[int] = None
    is_admin: bool = False


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


class UserResponse(ORMModel):
    id: int
    email: str
    full_name: str
    company_name: Optional[str] = None
    role: str
    complex_id: Optional[int] = None
    is_active: bool
    is_admin: bool


class ResidentialComplexCreate(BaseModel):
    # name: str
    address: Optional[str] = None
    ujin_complex_id: Optional[str] = None


class ResidentialComplexResponse(ORMModel):
    id: int
    name: str
    address: Optional[str] = None
    ujin_complex_id: Optional[str] = None
    is_active: bool
    displays_count: int = 0
    buildings_count: int = 0

    class Config:
        from_attributes = True


class BuildingCreate(BaseModel):
    complex_id: int
    name: str
    address: Optional[str] = None
    building_number: Optional[str] = None
    ujin_building_id: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class BuildingResponse(ORMModel):
    id: int
    complex_id: int
    name: str
    address: Optional[str] = None
    building_number: Optional[str] = None
    ujin_building_id: Optional[str] = None
    is_active: bool
    meta: Dict[str, Any] = Field(default_factory=dict)
    displays_count: int = 0

    class Config:
        from_attributes = True


class UjinTokenCreate(BaseModel):
    complex_id: Optional[int] = None
    name: str = "default"
    base_url: str
    token: str
    meta: Dict[str, Any] = Field(default_factory=dict)


class UjinTokenResponse(ORMModel):
    id: int
    complex_id: Optional[int] = None
    name: str
    base_url: str
    is_active: bool
    last_sync_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class DisplayCreate(BaseModel):
    complex_id: int
    name: str
    code: str
    location_type: str = "hall"
    location_title: Optional[str] = None
    entrance: Optional[str] = None
    floor: Optional[str] = None
    orientation: str = "portrait"
    resolution_width: int = 1080
    resolution_height: int = 1920
    building_id: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("orientation")
    @classmethod
    def validate_orientation(cls, value: str) -> str:
        if value not in {"portrait", "landscape"}:
            raise ValueError("orientation must be 'portrait' or 'landscape'")
        return value

    @field_validator("building_id", mode="before")
    @classmethod
    def empty_building_id_to_none(cls, value):
        if value in (0, "0", "", None):
            return None
        return value


class DisplayUpdate(BaseModel):
    name: Optional[str] = None
    location_type: Optional[str] = None
    location_title: Optional[str] = None
    entrance: Optional[str] = None
    floor: Optional[str] = None
    orientation: Optional[str] = None
    resolution_width: Optional[int] = None
    resolution_height: Optional[int] = None
    current_template_id: Optional[int] = None
    building_id: Optional[int] = None
    is_online: Optional[bool] = None
    is_active: Optional[bool] = None
    meta: Optional[Dict[str, Any]] = None


class DisplayStatusUpdate(BaseModel):
    is_online: Optional[bool] = None
    is_active: Optional[bool] = None
    last_seen_at: Optional[datetime] = None


class DisplayResponse(ORMModel):
    id: int
    complex_id: int
    building_id: Optional[int] = None
    name: str
    code: str
    location_type: str
    location_title: Optional[str] = None
    entrance: Optional[str] = None
    floor: Optional[str] = None
    orientation: str
    resolution_width: int
    resolution_height: int
    current_template_id: Optional[int] = None
    is_online: bool
    is_active: bool
    last_seen_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class DisplayGroupCreate(BaseModel):
    complex_id: int
    name: str
    description: Optional[str] = None
    building_id: Optional[int] = None
    display_ids: List[int] = Field(default_factory=list)


class DisplayGroupResponse(ORMModel):
    id: int
    complex_id: int
    building_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    is_active: bool


class WidgetConfig(BaseModel):
    type: str
    source: str = "local"
    title: Optional[str] = None
    x: int = 0
    y: int = 0
    w: int = 1
    h: int = 1
    settings: Dict[str, Any] = Field(default_factory=dict)


class TemplateCreate(BaseModel):
    # complex_id: int | None
    name: str
    theme: str = "dark"
    grid_config: Dict[str, Any] = Field(default_factory=lambda: {"columns": 4, "gap": 16})
    style_config: Dict[str, Any] = Field(default_factory=dict)
    widgets: List[WidgetConfig] = Field(default_factory=list)
    is_default: bool = False


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    theme: Optional[str] = None
    grid_config: Optional[Dict[str, Any]] = None
    style_config: Optional[Dict[str, Any]] = None
    widgets: Optional[List[WidgetConfig]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class TemplateResponse(ORMModel):
    id: int
    # complex_id: int
    name: str
    theme: str
    grid_config: Dict[str, Any] = Field(default_factory=dict)
    style_config: Dict[str, Any] = Field(default_factory=dict)
    widgets: List[Dict[str, Any]] = Field(default_factory=list)
    is_active: bool
    is_default: bool
    created_by_user_id: Optional[int] = None


class TemplateSendRequest(BaseModel):
    template_id: int
    target_type: TargetType = TargetType.display
    display_id: Optional[int] = None
    group_id: Optional[int] = None


class ContentItemCreate(BaseModel):
    complex_id: int
    title: str
    body: Optional[str] = None
    content_type: str = "static_info"
    image_url: Optional[str] = None
    file_url: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    publish_from: Optional[datetime] = None
    publish_to: Optional[datetime] = None


class ContentItemUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    content_type: Optional[str] = None
    image_url: Optional[str] = None
    file_url: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    publish_from: Optional[datetime] = None
    publish_to: Optional[datetime] = None


class ContentItemResponse(ORMModel):
    id: int
    complex_id: int
    title: str
    body: Optional[str] = None
    content_type: str
    image_url: Optional[str] = None
    file_url: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool
    publish_from: Optional[datetime] = None
    publish_to: Optional[datetime] = None


class EmergencyActivate(BaseModel):
    target_type: TargetType = TargetType.display
    display_id: Optional[int] = None
    group_id: Optional[int] = None
    emergency_text: str = Field(min_length=1, max_length=1000)
    priority: int = 1
    duration_minutes: Optional[int] = 30
    complex_id:Optional[int] = None


class EmergencyReset(BaseModel):
    target_type: TargetType = TargetType.display
    display_id: Optional[int] = None
    group_id: Optional[int] = None
    complex_id: Optional[int] = None


class EmergencyStateResponse(ORMModel):
    id: int
    complex_id: int
    target_type: str
    display_id: Optional[int] = None
    group_id: Optional[int] = None
    emergency_text: str
    priority: int
    is_active: bool
    activated_by_user_id: Optional[int] = None
    activated_at: datetime
    expires_at: Optional[datetime] = None
    reset_at: Optional[datetime] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class EmergencyLogResponse(ORMModel):
    id: int
    complex_id: int
    action: str
    target_type: str
    target_id: Optional[int] = None
    emergency_text: Optional[str] = None
    priority: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime
    meta: Dict[str, Any] = Field(default_factory=dict)

class DisplayPayload(BaseModel):
    display: DisplayResponse
    template: Optional[TemplateResponse] = None
    content_items: List[ContentItemResponse] = Field(default_factory=list)
    emergency: Optional[EmergencyStateResponse] = None
    ujin_data: Dict[str, Any] = Field(default_factory=dict)

class UjinSyncRequest(BaseModel):
    complex_id: int
    sync_complex: bool = True
    sync_buildings: bool = True
    sync_news: bool = True
    sync_parking: bool = True
    sync_storage: bool = True


class UjinSyncResponse(BaseModel):
    complex_id: int
    ujin_complex_id: Optional[str] = None
    synced_complex: bool = False
    buildings_created: int = 0
    buildings_updated: int = 0
    news_created: int = 0
    news_updated: int = 0
    parking_items: int = 0
    storage_items: int = 0

class UjinWidgetData(BaseModel):
    news: List[Dict[str, Any]] = Field(default_factory=list)
    parking: Dict[str, Any] = Field(default_factory=dict)
    storage: Dict[str, Any] = Field(default_factory=dict)