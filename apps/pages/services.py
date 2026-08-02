from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import frontmatter
import markdown
from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

logger = logging.getLogger(__name__)

BLOG_TITLE = "CiteGuild Blog"
BLOG_DESCRIPTION = "AI-native editorial source network for relevant agent-discovered citations"
BLOG_DEFAULT_AUTHOR = "LVTD LLC"
BLOG_DEFAULT_AUTHOR_URL = "https://lvtd.dev"
BLOG_DEFAULT_IMAGE_PARAMS = {
    "site": "x",
    "style": "logo",
    "font": "markerfelt",
    "title": BLOG_TITLE,
    "subtitle": BLOG_DESCRIPTION,
}
BLOG_DEFAULT_IMAGE_URL = "https://osig.app/g?" + urlencode(BLOG_DEFAULT_IMAGE_PARAMS)
BLOG_MARKDOWN_EXTENSIONS = ["fenced_code", "tables"]
BLOG_REQUIRED_FRONTMATTER = ("title", "description", "published_at")
BLOG_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BlogPostNotFound(Exception):
    pass


class BlogPostValidationError(ValueError):
    pass


@dataclass(frozen=True)
class BlogPost:
    slug: str
    title: str
    description: str
    content: str
    html: str
    published_at: datetime
    updated_at: datetime
    author: str
    keywords: tuple[str, ...]
    topics: tuple[str, ...]
    canonical_url: str
    image_url: str
    image_alt: str
    robots: str
    source_path: Path

    def get_absolute_url(self) -> str:
        return reverse("blog_post", kwargs={"slug": self.slug})

    @property
    def reading_time_minutes(self) -> int:
        words = re.findall(r"\w+", self.content)
        return max(1, round(len(words) / 225))

    @property
    def metadata_keywords(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys([*self.keywords, *self.topics]))


def blog_posts_dir() -> Path:
    return Path(settings.BLOG_POSTS_DIR)


def build_absolute_public_url(path: str) -> str:
    parsed = urlsplit(path)
    if parsed.scheme and parsed.netloc:
        return path
    return f"{settings.SITE_URL.rstrip('/')}/{path.lstrip('/')}"


def is_blog_slug(value: str) -> bool:
    return bool(BLOG_SLUG_PATTERN.fullmatch(value))


def _coerce_string(value, field_name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    raise BlogPostValidationError(f"{field_name} must be a string")


def _coerce_string_list(value, field_name: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        values = [str(part).strip() for part in value]
    else:
        raise BlogPostValidationError(f"{field_name} must be a string or list")
    return tuple(part for part in values if part)


def _ensure_aware(value: datetime) -> datetime:
    if timezone.is_aware(value):
        return value
    return timezone.make_aware(value, timezone.get_default_timezone())


def _coerce_datetime(value, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return _ensure_aware(datetime.combine(value, time.min))
    if isinstance(value, str):
        parsed_datetime = parse_datetime(value)
        if parsed_datetime is not None:
            return _ensure_aware(parsed_datetime)
        parsed_date = parse_date(value)
        if parsed_date is not None:
            return _ensure_aware(datetime.combine(parsed_date, time.min))
    raise BlogPostValidationError(f"{field_name} must be a date or datetime")


def _validate_required_frontmatter(metadata: dict, path: Path) -> None:
    missing = [field for field in BLOG_REQUIRED_FRONTMATTER if not metadata.get(field)]
    if missing:
        fields = ", ".join(missing)
        raise BlogPostValidationError(f"{path.name} missing required frontmatter: {fields}")


def load_blog_post(path: Path, *, content_dir: Path | None = None) -> BlogPost:
    content_dir = content_dir or blog_posts_dir()
    slug = path.relative_to(content_dir).with_suffix("").as_posix()
    if "/" in slug or not is_blog_slug(slug):
        raise BlogPostValidationError(f"{path.name} must use a lowercase filename slug")

    try:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BlogPostValidationError(f"{path.name} has invalid frontmatter") from exc

    metadata = dict(post.metadata)
    _validate_required_frontmatter(metadata, path)

    title = _coerce_string(metadata.get("title"), "title")
    description = _coerce_string(metadata.get("description"), "description")
    published_at = _coerce_datetime(metadata.get("published_at"), "published_at")
    updated_at = _coerce_datetime(metadata.get("updated_at", published_at), "updated_at")
    author = _coerce_string(metadata.get("author", BLOG_DEFAULT_AUTHOR), "author")
    keywords = _coerce_string_list(metadata.get("keywords"), "keywords")
    topics = _coerce_string_list(metadata.get("topics"), "topics")
    canonical_url = _coerce_string(metadata.get("canonical_url"), "canonical_url")
    image = _coerce_string(metadata.get("image"), "image")
    image_alt = _coerce_string(metadata.get("image_alt"), "image_alt")
    robots = _coerce_string(metadata.get("robots", "index, follow"), "robots")

    content = post.content.strip()
    html = markdown.markdown(content, extensions=BLOG_MARKDOWN_EXTENSIONS)

    return BlogPost(
        slug=slug,
        title=title,
        description=description,
        content=content,
        html=html,
        published_at=published_at,
        updated_at=updated_at,
        author=author,
        keywords=keywords,
        topics=topics,
        canonical_url=canonical_url
        or build_absolute_public_url(reverse("blog_post", kwargs={"slug": slug})),
        image_url=build_absolute_public_url(image) if image else BLOG_DEFAULT_IMAGE_URL,
        image_alt=image_alt,
        robots=robots,
        source_path=path,
    )


def list_blog_posts() -> list[BlogPost]:
    content_dir = blog_posts_dir()
    if not content_dir.exists():
        return []

    posts = []
    for path in content_dir.glob("*.md"):
        try:
            posts.append(load_blog_post(path, content_dir=content_dir))
        except BlogPostValidationError:
            logger.warning(
                "blog.post.load.completed",
                extra={
                    "event.name": "blog.post.load.completed",
                    "post_slug": path.stem,
                    "outcome": "failure",
                    "error.type": "BlogPostValidationError",
                },
            )
    return sorted(posts, key=lambda post: (post.published_at, post.slug), reverse=True)


def get_blog_post(slug: str) -> BlogPost:
    if not is_blog_slug(slug):
        raise BlogPostNotFound(slug)

    content_dir = blog_posts_dir()
    path = content_dir / f"{slug}.md"
    if not path.exists():
        raise BlogPostNotFound(slug)
    return load_blog_post(path, content_dir=content_dir)


def iter_blog_post_validation_errors() -> list[BlogPostValidationError]:
    content_dir = blog_posts_dir()
    if not content_dir.exists():
        return []

    errors = []
    for path in sorted(content_dir.glob("*.md")):
        try:
            load_blog_post(path, content_dir=content_dir)
        except BlogPostValidationError as exc:
            errors.append(exc)
    return errors


def blog_index_url() -> str:
    return build_absolute_public_url(reverse("blog_posts"))


def author_schema(name: str, author_url: str = BLOG_DEFAULT_AUTHOR_URL) -> dict:
    schema = {"@type": "Person", "name": name}
    if author_url:
        schema["url"] = author_url
    return schema


def publisher_schema() -> dict:
    return {
        "@type": "Organization",
        "name": "CiteGuild",
        "logo": {
            "@type": "ImageObject",
            "url": build_absolute_public_url(static("images/citeguild-logo.svg")),
        },
    }


def blog_post_schema(post: BlogPost) -> dict:
    schema = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post.title,
        "description": post.description,
        "image": post.image_url,
        "url": post.canonical_url,
        "datePublished": post.published_at.isoformat(),
        "dateModified": post.updated_at.isoformat(),
        "author": author_schema(post.author),
        "publisher": publisher_schema(),
        "articleBody": post.content,
        "mainEntityOfPage": {"@type": "WebPage", "@id": post.canonical_url},
    }
    if post.metadata_keywords:
        schema["keywords"] = list(post.metadata_keywords)
    return schema


def blog_index_schema(posts: list[BlogPost]) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Blog",
        "name": BLOG_TITLE,
        "description": BLOG_DESCRIPTION,
        "url": blog_index_url(),
        "publisher": publisher_schema(),
        "blogPost": [
            {
                "@type": "BlogPosting",
                "headline": post.title,
                "description": post.description,
                "url": post.canonical_url,
                "datePublished": post.published_at.isoformat(),
            }
            for post in posts
        ],
    }


def json_ld(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
