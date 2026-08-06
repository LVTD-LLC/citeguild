import logging
from pathlib import Path

import frontmatter
import markdown
import yaml
from allauth.account.views import SignupByPasskeyView, SignupView
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.template import Context, Template
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.analytics import SIGNUP_COMPLETED, has_analytics_consent, track_event
from apps.core.choices import ProfileStates
from apps.core.models import Profile
from apps.core.views import build_absolute_public_url, build_agent_setup_prompt
from apps.pages.services import (
    BLOG_DEFAULT_IMAGE_URL,
    BLOG_DESCRIPTION,
    BLOG_TITLE,
    BlogPostNotFound,
    BlogPostValidationError,
    blog_index_schema,
    blog_index_url,
    blog_post_schema,
    get_blog_post,
    homepage_schema,
    json_ld,
    list_blog_posts,
    use_case_page_schema,
)

logger = logging.getLogger(__name__)
DOCS_CONTENT_ROOT = Path(settings.BASE_DIR) / "apps" / "pages" / "content" / "docs"
DOCS_NAVIGATION_PATH = DOCS_CONTENT_ROOT / "navigation.yaml"


class LandingPageView(TemplateView):
    template_name = "pages/landing-page.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        payment_status = self.request.GET.get("payment")
        if payment_status == "success":
            messages.success(self.request, "Thanks for subscribing, I hope you enjoy the app!")
        elif payment_status == "failed":
            messages.error(self.request, "Something went wrong with the payment.")
        context["schema_json"] = json_ld(homepage_schema())
        return context


class SignupTrackingMixin:
    tracking_source_name = "signup"

    def _track_signup(self):
        user = self.user
        profile = user.profile
        if has_analytics_consent(self.request):
            track_event(
                profile,
                SIGNUP_COMPLETED,
                {"signup_method": self.tracking_source_name},
                current_state=ProfileStates.SIGNED_UP,
                source_function=f"{self.tracking_source_name} - form_valid",
            )

    def form_valid(self, form):
        response = super().form_valid(form)
        self._track_signup()
        return response


class AccountSignupView(SignupTrackingMixin, SignupView):
    # signup.html uses allauth's injected entrance context for passkey signup
    # keys such as PASSKEY_SIGNUP_ENABLED and signup_by_passkey_url.
    template_name = "account/signup.html"
    tracking_source_name = "password"


class AccountSignupByPasskeyView(SignupTrackingMixin, SignupByPasskeyView):
    template_name = "account/signup_by_passkey.html"
    tracking_source_name = "passkey"


class PricingView(TemplateView):
    template_name = "pages/pricing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.user.is_authenticated:
            try:
                profile = self.request.user.profile
                context["has_pro_subscription"] = profile.has_active_subscription
            except Profile.DoesNotExist:
                context["has_pro_subscription"] = False
        else:
            context["has_pro_subscription"] = False

        return context


class SaasLinkBuildingView(TemplateView):
    template_name = "pages/for/saas-link-building.html"
    faqs = [
        (
            "What is SaaS link building?",
            "SaaS link building is the work of earning relevant editorial links "
            "to a software company's useful pages. Strong links begin with a "
            "real reader need and a source that helps answer it.",
        ),
        (
            "Does CiteGuild guarantee backlinks?",
            "No. CiteGuild makes eligible member articles searchable to writing "
            "agents. The agent decides whether a source fits its draft, and the "
            "publisher retains control over anything it publishes.",
        ),
        (
            "Does CiteGuild require reciprocal links or credits?",
            "No. CiteGuild does not balance credits, require reciprocal links, "
            "sell placements, or prescribe anchor text.",
        ),
        (
            "How do SaaS articles become searchable in CiteGuild?",
            "A paid member submits a public sitemap. CiteGuild indexes eligible "
            "articles and exposes relevance-ranked retrieval through MCP, CLI, "
            "and API.",
        ),
        (
            "Does CiteGuild automatically insert or publish a source?",
            "No. CiteGuild returns source candidates and context for evaluation. "
            "The writing agent or publisher decides whether a citation helps and "
            "controls any separate publishing workflow.",
        ),
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["schema_json"] = json_ld(
            use_case_page_schema(
                name="SaaS link building",
                path=reverse("saas_link_building"),
                questions_and_answers=self.faqs,
            )
        )
        return context


class PrivacyPolicyView(TemplateView):
    template_name = "pages/privacy-policy.html"


class TermsOfServiceView(TemplateView):
    template_name = "pages/terms-of-service.html"


def blog_posts_view(request):
    blog_posts = list_blog_posts()
    return render(
        request,
        "pages/blog/blog_posts.html",
        {
            "blog_title": BLOG_TITLE,
            "blog_description": BLOG_DESCRIPTION,
            "blog_image_url": BLOG_DEFAULT_IMAGE_URL,
            "blog_posts": blog_posts,
            "canonical_url": blog_index_url(),
            "schema_json": json_ld(blog_index_schema(blog_posts)),
        },
    )


def blog_post_view(request, slug):
    try:
        blog_post = get_blog_post(slug)
    except (BlogPostNotFound, BlogPostValidationError) as exc:
        raise Http404("Blog post not found") from exc

    return render(
        request,
        "pages/blog/blog_post.html",
        {
            "blog_post": blog_post,
            "canonical_url": blog_post.canonical_url,
            "schema_json": json_ld(blog_post_schema(blog_post)),
        },
    )


def load_navigation_config():
    """
    Load documentation navigation configuration from YAML.
    Returns an empty dict if the file is missing or invalid.
    """
    if not DOCS_NAVIGATION_PATH.exists():
        return {}

    try:
        with open(DOCS_NAVIGATION_PATH, encoding="utf-8") as file:
            config = yaml.safe_load(file)
            return config.get("navigation", {}) if config else {}
    except Exception:
        return {}


def get_page_title(markdown_file, fallback):
    try:
        with open(markdown_file, encoding="utf-8") as file:
            post = frontmatter.load(file)
        return post.get("title", fallback)
    except Exception:
        return fallback


def get_category_title(category_slug):
    if category_slug == "api-reference":
        return "API Reference"
    return category_slug.replace("-", " ").title()


def get_docs_navigation():  # noqa: C901
    """
    Build navigation from the pages app's docs content directory.
    Uses navigation.yaml ordering when defined, then falls back to alphabetical order.
    """
    navigation = []

    if not DOCS_CONTENT_ROOT.exists():
        return navigation

    all_categories = {}
    for category_dir in DOCS_CONTENT_ROOT.iterdir():
        if category_dir.is_dir():
            category_slug = category_dir.name
            all_categories[category_slug] = category_dir

    navigation_config = load_navigation_config()

    ordered_categories = []
    for category_slug in navigation_config.keys():
        if category_slug in all_categories:
            ordered_categories.append(category_slug)

    remaining_categories = sorted(set(all_categories.keys()) - set(ordered_categories))
    ordered_categories.extend(remaining_categories)

    for category_slug in ordered_categories:
        category_dir = all_categories[category_slug]
        category_name = get_category_title(category_slug)

        all_pages = {}
        for markdown_file in category_dir.glob("*.md"):
            page_slug = markdown_file.stem
            all_pages[page_slug] = markdown_file

        custom_page_order = navigation_config.get(category_slug, [])

        ordered_pages = []
        for page_slug in custom_page_order:
            if page_slug in all_pages:
                ordered_pages.append(page_slug)

        remaining_pages = sorted(set(all_pages.keys()) - set(ordered_pages))
        ordered_pages.extend(remaining_pages)

        pages = []
        for page_slug in ordered_pages:
            page_title = page_slug.replace("-", " ").title()
            pages.append(
                {
                    "slug": page_slug,
                    "title": get_page_title(all_pages[page_slug], page_title),
                    "url": f"/docs/{category_slug}/{page_slug}/",
                }
            )

        if pages:
            navigation.append(
                {
                    "category": category_name,
                    "category_slug": category_slug,
                    "pages": pages,
                }
            )

    return navigation


def get_flat_page_list(navigation):
    """
    Flatten the navigation structure into a single list of pages in order.
    Returns dicts with category_slug, page_slug, page_title, and url.
    """
    flat_pages = []
    for category_item in navigation:
        for page_item in category_item["pages"]:
            flat_pages.append(
                {
                    "category_slug": category_item["category_slug"],
                    "page_slug": page_item["slug"],
                    "page_title": page_item["title"],
                    "url": page_item["url"],
                }
            )
    return flat_pages


def get_previous_and_next_pages(navigation, current_category, current_page):
    """
    Find the previous and next pages in the documentation navigation.
    Returns a tuple of (previous_page, next_page) where each is a dict or None.
    """
    flat_pages = get_flat_page_list(navigation)

    current_index = None
    for index, page_item in enumerate(flat_pages):
        if (
            page_item["category_slug"] == current_category
            and page_item["page_slug"] == current_page
        ):
            current_index = index
            break

    if current_index is None:
        return None, None

    previous_page = flat_pages[current_index - 1] if current_index > 0 else None
    next_page = flat_pages[current_index + 1] if current_index < len(flat_pages) - 1 else None

    return previous_page, next_page


@login_required
def docs_home_view(request):
    return redirect(
        reverse("docs_page", kwargs={"category": "getting-started", "page": "introduction"})
    )


@login_required
def docs_page_view(request, category, page):
    """
    Render an authenticated documentation page from markdown with frontmatter and user context.
    """
    markdown_file = DOCS_CONTENT_ROOT / category / f"{page}.md"

    if not markdown_file.exists():
        raise Http404("Documentation page not found") from None

    try:
        with open(markdown_file, encoding="utf-8") as file:
            post = frontmatter.load(file)

        docs_template_context = {
            "api_base_url": build_absolute_public_url("/api/").rstrip("/"),
            "api_key_env_var": "CITEGUILD_API_KEY",
            "api_docs_url": build_absolute_public_url("/api/docs"),
            "agent_setup_prompt": build_agent_setup_prompt(),
            "mcp_url": build_absolute_public_url("/mcp/"),
            "agent_instructions_url": build_absolute_public_url("/AGENTS.md"),
            "site_url": build_absolute_public_url("/").rstrip("/"),
            "user_email": request.user.email,
        }
        rendered_markdown = Template(post.content).render(Context(docs_template_context))
        markdown_html = markdown.markdown(rendered_markdown, extensions=["fenced_code", "tables"])

        navigation = get_docs_navigation()
        previous_page, next_page = get_previous_and_next_pages(navigation, category, page)

        default_page_title = page.replace("-", " ").title()
        default_category_title = get_category_title(category)

        context = {
            "content": markdown_html,
            "navigation": navigation,
            "current_category": category,
            "current_page": page,
            "page_title": post.get("title", default_page_title),
            "category_title": default_category_title,
            "meta_description": post.get("description", ""),
            "author": post.get("author", ""),
            "canonical_url": post.get("canonical_url", ""),
            "previous_page": previous_page,
            "next_page": next_page,
        }

        return render(request, "pages/docs/docs_page.html", context)
    except Exception as error:
        logger.error(
            "documentation.page.load.completed",
            extra={
                "event.name": "documentation.page.load.completed",
                "category": category,
                "page": page,
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
            exc_info=True,
        )
        raise Http404("Documentation page not found") from None
