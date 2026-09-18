from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class UserResponse(BaseModel):
    id: int
    username: str
    actual_name: str = "N/A"
    profile_url: str
    rating: Optional[float] = None
    total_questions: int = 0
    easy_questions: int = 0
    medium_questions: int = 0
    hard_questions: int = 0
    college_relevance: str = "unknown"
    source_user: Optional[str] = None
    discovered_via: str = "seed"
    crawl_status: str = "pending"
    stats_status: str = "pending"
    retry_count: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserListResponse(BaseModel):
    total: int
    page: int
    limit: int
    pages: int
    users: List[UserResponse]


class CollectorStatus(BaseModel):
    is_running: bool
    current_action: str
    target: int
    discovered: int
    cached: int
    new_users: int
    processed: int
    successful: int
    stats_completed: int
    failed: int
    pending: int
    mnnit_count: int


class CollectorActionResponse(BaseModel):
    status: str
    message: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    status: str
    message: str
    token: str
    username: str


class AdminUserUpdateRequest(BaseModel):
    username: str


class AdminUserUpdateDetail(BaseModel):
    username: str
    actual_name: str = "N/A"
    rating: Optional[float] = None
    rating_display: str = "N/A"
    unrated_reason: Optional[str] = None
    total_questions: int = 0
    easy_questions: int = 0
    medium_questions: int = 0
    hard_questions: int = 0
    college_relevance: str = "unknown"
    last_updated: Optional[str] = None


class AdminUserUpdateResponse(BaseModel):
    status: str
    message: str
    is_new: bool = False
    user: Optional[AdminUserUpdateDetail] = None


class AdminDiscoverRequest(BaseModel):
    target: int = 1000


class AdminAuditLogItem(BaseModel):
    id: int
    timestamp: Optional[str] = None
    admin_username: str
    action: str
    target: Optional[str] = None
    status: str
    details: Optional[str] = None

