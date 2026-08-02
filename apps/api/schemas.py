from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import ConfigDict, Field

ExcludedDomain = Annotated[
    str,
    Field(
        min_length=1,
        max_length=253,
        pattern=(
            r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$"
        ),
    ),
]
SearchLanguage = Annotated[
    str,
    Field(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"),
]


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


class APIErrorOut(Schema):
    code: str
    message: str
    retryable: bool
    request_id: str


class ProjectStatusOut(Schema):
    id: UUID
    name: str
    sitemap_url: str
    normalized_host: str
    state: str
    article_count: int
    active_article_count: int
    last_sync_at: datetime | None
    current_sync_started_at: datetime | None
    last_error_code: str


class ProjectListOut(Schema):
    count: int
    limit: int
    offset: int
    results: list[ProjectStatusOut]


class ProjectListParams(Schema):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10_000)


class SearchRequest(Schema):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "query": "How do Django transaction commit hooks work?",
                    "limit": 10,
                    "language": "en",
                    "excluded_domains": ["my-site.example"],
                }
            ]
        },
    )

    query: str = Field(min_length=1, max_length=8_000, pattern=r"\S")
    limit: int = Field(default=10, ge=1, le=50, strict=True)
    language: SearchLanguage | None = Field(default=None, max_length=35)
    excluded_domains: list[ExcludedDomain] = Field(default_factory=list, max_length=20)


class SearchResultOut(Schema):
    article_id: UUID
    title: str = Field(max_length=300)
    canonical_url: str = Field(max_length=2_048)
    domain: str = Field(max_length=253)
    excerpt: str = Field(max_length=320)
    relevance: float = Field(ge=0, le=1)
    language: str = Field(max_length=35)
    last_seen_at: datetime


class SearchResponseOut(Schema):
    contract_version: Literal["v1"]
    results: list[SearchResultOut]
