from datetime import datetime
from uuid import UUID

from ninja import Schema


class ProfileSettingsOut(Schema):
    has_pro_subscription: bool


class UserSettingsOut(Schema):
    profile: ProfileSettingsOut


class UserProfileOut(Schema):
    id: int
    state: str
    has_active_subscription: bool


class UserInfoOut(Schema):
    id: int
    email: str
    username: str
    first_name: str
    last_name: str
    full_name: str
    date_joined: datetime
    profile: UserProfileOut


class ProjectSubmissionIn(Schema):
    name: str
    sitemap_url: str


class ProjectSubmissionOut(Schema):
    id: UUID
    name: str
    sitemap_url: str
    normalized_host: str
    state: str
    sitemap_kind: str
    sync_request_id: UUID
    sync_state: str


class ProjectSubmissionErrorOut(Schema):
    code: str
    message: str
    retryable: bool
