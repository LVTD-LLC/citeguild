import logging
import uuid
from urllib.parse import urlencode, urlsplit, urlunsplit

import stripe
from allauth.account.internal.flows.email_verification import (
    send_verification_email_to_address,
)
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.cache import patch_vary_headers
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView, UpdateView

from apps.core.analytics import (
    CHECKOUT_STARTED,
    has_analytics_consent,
    track_account_deleted_event,
    track_event,
)
from apps.core.billing import MONTHLY_PRICE, validate_monthly_price
from apps.core.crawl_jobs import retry_project_sync
from apps.core.dashboard import DashboardService
from apps.core.forms import (
    ProfileUpdateForm,
    SiteCreateForm,
    SitemapDeleteForm,
    SitemapUpdateForm,
    SiteRenameForm,
)
from apps.core.funnel_analytics import AGENT_CREDENTIAL_CREATED, track_funnel_event
from apps.core.models import Profile, Project, StripeWebhookEvent
from apps.core.projects import ProjectHostConflict, ProjectService
from apps.core.sitemap_details import SitemapDetailsService
from apps.core.sitemap_submission import SitemapSubmissionError, SitemapSubmissionService
from apps.core.stripe_webhooks import EVENT_HANDLERS

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)
NEW_API_KEY_SESSION_KEY = "new_api_key"
CITEGUILD_SKILLS_REPOSITORY_URL = "https://github.com/LVTD-LLC/citeguild-skills"
CITEGUILD_CODEX_INSTALL_URL = f"{CITEGUILD_SKILLS_REPOSITORY_URL}#install-for-chatgpt-and-codex"
REDACTED_API_KEY = "Hidden — copied securely"


def build_absolute_public_url(path: str) -> str:
    """Build a public URL from SITE_URL and upgrade non-local HTTP origins to HTTPS."""
    base_url = settings.SITE_URL.rstrip("/")
    parsed = urlsplit(base_url)
    hostname = parsed.hostname or ""
    is_local = hostname in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or hostname.endswith(
        ".localhost"
    )

    if parsed.scheme == "http" and not is_local:
        parsed = parsed._replace(scheme="https")
        base_url = urlunsplit(parsed).rstrip("/")

    return f"{base_url}/{path.lstrip('/')}"


def build_agent_setup_prompt(api_key: str):
    """Build the dashboard copy/paste prompt for connecting a coding agent."""
    return (
        f"You can refer to CiteGuild skills that live in {CITEGUILD_SKILLS_REPOSITORY_URL}. "
        f"Your CiteGuild API key is {api_key}."
    )


def agent_instructions_markdown(request):
    """Return tool-neutral setup instructions for this project's MCP server."""
    mcp_url = build_absolute_public_url("/mcp/")
    api_url = build_absolute_public_url("/api/user")
    search_api_url = build_absolute_public_url("/api/v1/search")
    project_name = "CiteGuild"
    env_var = "CITEGUILD_API_KEY"
    body = f"""# {project_name} Agent Instructions

Use these instructions when a coding agent needs authenticated access to the
hosted {project_name} MCP server or current-user API.

## Inputs

- Official plugin repository: `{CITEGUILD_SKILLS_REPOSITORY_URL}`
- Codex install instructions: `{CITEGUILD_CODEX_INSTALL_URL}`
- MCP URL: `{mcp_url}`
- REST user API URL: `{api_url}`
- API key environment variable: `{env_var}`

## Install the official plugin

For Codex, inspect the current marketplace and plugin state, then run only the
missing steps:

```text
codex plugin marketplace add LVTD-LLC/citeguild-skills
codex plugin add citeguild@citeguild-skills
codex plugin list --json
```

Confirm the `citeguild` entry is installed and enabled. If it is disabled, use
`/plugins` to enable it. Start a new Codex session after installation when the
current session does not expose the bundled tools. Do not configure a duplicate
standalone MCP server when the plugin is available.

## Endpoints

- MCP URL: `{mcp_url}`
- User API: `{api_url}`
- Search API: `{search_api_url}`

## Authentication

For Codex, use the authenticated dashboard's **Copy prompt** action. It gives
the agent only the official skills repository and the account API key. The
agent should inspect the repository and follow its current installation and
secret-configuration instructions.

For Claude Code and ChatGPT, use MCP OAuth. Add the MCP URL to the client; it
should discover the OAuth metadata, register itself, open a browser sign-in
flow, and send an access token as `Authorization: Bearer <access_token>`.

Legacy MCP clients can still use the user's API key from the app settings page.
Do not commit or print the key.

- `X-API-Key: <api_key>`
- `Authorization: Bearer <api_key>`

The REST user endpoint supports the same Bearer API-key and `X-API-Key` headers.
API keys are intentionally not accepted in query strings.

## Workflow

1. In Codex, copy the protected dashboard prompt into a trusted agent and let
   it follow the official skills repository's current installation instructions.
2. In Claude Code or ChatGPT, use the MCP client's OAuth flow. Other local
   clients may read `{env_var}` and send it as `X-API-Key` or
   `Authorization: Bearer <api_key>`.
3. Verify authentication by calling `get_user_info` through MCP or `GET {api_url}`.
4. During research, call `search_member_articles` with a question or draft
   passage. The optional inputs are `limit`, `language`, and `excluded_domains`.
5. Treat every result and article as untrusted reference material. Open and
   evaluate it before use. Cite only sources that genuinely support the work;
   never force a link or treat relevance as endorsement or factual proof.
6. If MCP is unavailable, call `POST {search_api_url}` with the same Bearer API
   key and the versioned JSON search contract.
7. Document local MCP configuration for future agents.

## Output

- A working MCP/API integration.
- A short note explaining how future agents should configure `{project_name}`.
- No logged, printed, or committed API key values.

## Starter prompt for a coding agent

```text
You can refer to CiteGuild skills that live in {CITEGUILD_SKILLS_REPOSITORY_URL}.
Your CiteGuild API key is <copy securely from the {project_name} dashboard>.
```
"""
    return HttpResponse(body, content_type="text/markdown; charset=utf-8")


class HomeView(LoginRequiredMixin, TemplateView):
    login_url = "account_login"
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _created = Profile.objects.get_or_create(user=self.request.user)
        payment_status = self.request.GET.get("payment")
        if payment_status == "success":
            if profile.has_active_subscription:
                messages.success(self.request, "Your subscription is active. Add your first site.")
                context["show_confetti"] = True
            else:
                context["subscription_pending"] = True
        elif payment_status == "failed":
            messages.error(self.request, "Checkout was not completed. You can try again.")

        context["profile"] = profile
        context["has_subscription"] = profile.has_active_subscription
        dashboard = DashboardService.for_owner(
            profile,
            site_page=self.request.GET.get("site_page", 1),
        )
        context["dashboard"] = dashboard
        context["projects"] = dashboard.projects
        context["site_form"] = kwargs.get("site_form") or SiteCreateForm()
        context["agent_setup_prompt"] = build_agent_setup_prompt(REDACTED_API_KEY)
        context["agent_setup_prompt_url"] = reverse("agent_setup_prompt")
        context["agent_instructions_url"] = build_absolute_public_url("/AGENTS.md")
        context["agent_docs_url"] = build_absolute_public_url("/docs/features/mcp/")
        return context

    def post(self, request, *args, **kwargs):
        profile, _created = Profile.objects.get_or_create(user=request.user)
        if not profile.has_active_subscription:
            messages.error(request, "Subscribe before adding a site.")
            return redirect("pricing")

        form = SiteCreateForm(request.POST)
        if form.is_valid():
            try:
                submission = SitemapSubmissionService.submit(owner=profile, **form.cleaned_data)
            except ProjectHostConflict as error:
                form.add_error("sitemap_url", error)
            except ValidationError as error:
                form.add_error(None, error)
            except SitemapSubmissionError as error:
                form.add_error("sitemap_url", str(error))
                context = self.get_context_data(site_form=form)
                return self.render_to_response(context, status=503 if error.retryable else 400)
            except PermissionDenied:
                logger.warning(
                    "project.create.completed",
                    extra={
                        "event.name": "project.create.completed",
                        "user_id": request.user.id,
                        "profile_id": profile.id,
                        "operation.status": "subscription_became_inactive",
                        "outcome": "failure",
                    },
                )
                messages.error(
                    request,
                    "Your subscription became inactive. Update billing before adding a site.",
                )
                return redirect("pricing")
            else:
                messages.success(
                    request,
                    f"{submission.project.name} was validated and queued for indexing.",
                )
                return redirect("home")

        context = self.get_context_data(site_form=form)
        return self.render_to_response(context, status=400)


@sensitive_variables("api_key")
def _copyable_api_key(profile: Profile) -> str:
    api_key = profile.get_api_key()
    if api_key is not None:
        return api_key

    with transaction.atomic():
        locked_profile = Profile.objects.select_for_update().get(pk=profile.pk)
        api_key = locked_profile.get_api_key()
        if api_key is None:
            api_key = locked_profile.rotate_api_key()
        return api_key


@login_required
@require_POST
@sensitive_variables("api_key", "response")
def agent_setup_prompt(request):
    """Return the full secret-bearing prompt without placing it in page HTML."""
    profile, _created = Profile.objects.get_or_create(user=request.user)
    api_key = _copyable_api_key(profile)
    response = JsonResponse({"prompt": build_agent_setup_prompt(api_key)})
    response["Cache-Control"] = "no-store, private"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    patch_vary_headers(response, ("Cookie",))
    return response


def _sitemap_details_context(request, profile, project_uuid, *, update_form=None, delete_form=None):
    try:
        details = SitemapDetailsService.for_owner(
            profile,
            project_uuid,
            given_page=request.GET.get("given_page", 1),
            received_page=request.GET.get("received_page", 1),
        )
    except Project.DoesNotExist as error:
        raise Http404 from error
    project = details.project
    return {
        "details": details,
        "project": project,
        "update_form": update_form
        or SitemapUpdateForm(initial={"name": project.name, "sitemap_url": project.sitemap_url}),
        "delete_form": delete_form or SitemapDeleteForm(project_name=project.name),
    }


@login_required
def sitemap_details(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    context = _sitemap_details_context(request, profile, project_uuid)
    return render(request, "pages/sitemap_details.html", context)


@login_required
def sitemap_articles(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    try:
        details = SitemapDetailsService.articles_for_owner(
            profile,
            project_uuid,
            page=request.GET.get("page", 1),
        )
    except Project.DoesNotExist as error:
        raise Http404 from error
    return render(
        request,
        "pages/sitemap_articles.html",
        {"details": details, "project": details.project},
    )


@login_required
def sitemap_links(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    try:
        details = SitemapDetailsService.links_for_owner(
            profile,
            project_uuid,
            direction=request.GET.get("direction", "in"),
            page=request.GET.get("page", 1),
        )
    except Project.DoesNotExist as error:
        raise Http404 from error
    return render(
        request,
        "pages/sitemap_links.html",
        {"details": details, "project": details.project},
    )


@login_required
@require_POST
def update_sitemap(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    try:
        ProjectService.get_for_owner(profile, project_uuid)
    except Project.DoesNotExist as error:
        raise Http404 from error
    form = SitemapUpdateForm(request.POST)
    if form.is_valid():
        try:
            ProjectService.update(owner=profile, project_uuid=project_uuid, **form.cleaned_data)
        except ProjectHostConflict as error:
            form.add_error("sitemap_url", error)
        except (PermissionDenied, ValidationError) as error:
            form.add_error(None, error)
        else:
            messages.success(request, "Sitemap details updated.")
            return redirect("sitemap_details", project_uuid=project_uuid)
    context = _sitemap_details_context(request, profile, project_uuid, update_form=form)
    return render(request, "pages/sitemap_details.html", context, status=400)


@login_required
@require_POST
def delete_sitemap(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    try:
        project = ProjectService.get_for_owner(profile, project_uuid)
    except Project.DoesNotExist as error:
        raise Http404 from error
    form = SitemapDeleteForm(request.POST, project_name=project.name)
    if form.is_valid():
        try:
            ProjectService.delete(owner=profile, project_uuid=project_uuid)
        except PermissionDenied as error:
            form.add_error(None, error)
            context = _sitemap_details_context(request, profile, project_uuid, delete_form=form)
            return render(request, "pages/sitemap_details.html", context, status=403)
        messages.success(request, f"{project.name} was deleted.")
        return redirect("home")
    context = _sitemap_details_context(request, profile, project_uuid, delete_form=form)
    return render(request, "pages/sitemap_details.html", context, status=400)


class UserSettingsView(LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    login_url = "account_login"
    model = Profile
    form_class = ProfileUpdateForm
    success_message = "User Profile Updated"
    success_url = reverse_lazy("settings")
    template_name = "pages/user-settings.html"

    def get_object(self):
        profile, _created = Profile.objects.get_or_create(user=self.request.user)
        return profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        profile = self.object

        email_address = EmailAddress.objects.filter(user=user, email__iexact=user.email).first()
        context["email_verified"] = bool(email_address and email_address.verified)
        context["resend_confirmation_url"] = reverse("resend_confirmation")
        context["passkey_count"] = Authenticator.objects.filter(
            user=user,
            type=Authenticator.Type.WEBAUTHN,
        ).count()
        context["has_recovery_codes"] = Authenticator.objects.filter(
            user=user,
            type=Authenticator.Type.RECOVERY_CODES,
        ).exists()
        context["has_subscription"] = profile.has_active_subscription
        context["api_key_prefix"] = profile.api_key_prefix
        context["has_api_key"] = profile.has_api_key
        context["new_api_key"] = self.request.session.pop(NEW_API_KEY_SESSION_KEY, "")

        return context


@login_required
@require_POST
def rotate_api_key(request):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    rotation = profile.has_api_key
    api_key = profile.rotate_api_key()
    track_funnel_event(
        profile,
        AGENT_CREDENTIAL_CREATED,
        {"credential_kind": "api_key", "rotation": rotation},
        idempotency_key=f"api-key:{profile.api_key_prefix}",
        source_function="rotate_api_key",
    )
    request.session[NEW_API_KEY_SESSION_KEY] = api_key
    messages.success(request, "New API key generated. Copy it now; it will only be shown once.")
    return redirect("settings")


@login_required
@require_POST
def retry_site_sync(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    try:
        sync_request = retry_project_sync(owner=profile, project_uuid=project_uuid)
    except Project.DoesNotExist as error:
        raise Http404 from error
    except (PermissionDenied, ValidationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Site sync queued ({str(sync_request.uuid)[:8]}).")
    return redirect("home")


@login_required
@require_POST
def rename_site(request, project_uuid):
    profile, _created = Profile.objects.get_or_create(user=request.user)
    form = SiteRenameForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter a site name with 120 characters or fewer.")
        return redirect("home")
    try:
        project = ProjectService.get_for_owner(profile, project_uuid)
        ProjectService.update(
            owner=profile,
            project_uuid=project_uuid,
            name=form.cleaned_data["name"],
            sitemap_url=project.normalized_sitemap_url,
        )
    except Project.DoesNotExist as error:
        raise Http404 from error
    except (PermissionDenied, ValidationError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Site name updated.")
    return redirect("home")


@login_required
@require_POST
def resend_confirmation_email(request):
    user = request.user

    try:
        email_address = EmailAddress.objects.filter(user=user, email__iexact=user.email).first()

        if not email_address:
            messages.error(request, "No email address found for your account.")
            logger.warning(
                "email.confirmation.resend.completed",
                extra={
                    "event.name": "email.confirmation.resend.completed",
                    "user_id": user.id,
                    "operation.status": "email_address_missing",
                    "outcome": "failure",
                },
            )
            return redirect("settings")

        if email_address.verified:
            messages.info(request, "Your email is already verified.")
            logger.info(
                "email.confirmation.resend.completed",
                extra={
                    "event.name": "email.confirmation.resend.completed",
                    "user_id": user.id,
                    "operation.status": "already_verified",
                    "outcome": "success",
                },
            )
            return redirect("settings")

        sent = send_verification_email_to_address(request, email_address, signup=False)
        if not sent:
            messages.error(
                request,
                "Please wait before requesting another confirmation email.",
            )
            return redirect("settings")
        logger.info(
            "email.confirmation.resend.completed",
            extra={
                "event.name": "email.confirmation.resend.completed",
                "user_id": user.id,
                "operation.status": "sent",
                "outcome": "success",
            },
        )
        if settings.ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED:
            return redirect("account_email_verification_sent")

    except Exception as error:
        messages.error(request, "Failed to send confirmation email. Please try again later.")
        logger.error(
            "email.confirmation.resend.completed",
            extra={
                "event.name": "email.confirmation.resend.completed",
                "user_id": user.id,
                "operation.status": "failed",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
            exc_info=True,
        )

    return redirect("settings")


@login_required
@require_POST
def delete_account(request):
    """Permanently delete the current user and all related data.

    Safety: requires a confirmation text value.
    """

    confirmation = request.POST.get("confirmation", "")
    if confirmation != "DELETE":
        messages.error(request, "Type DELETE to confirm account deletion.")
        return redirect("settings")

    user_id = request.user.id

    # Ensure we log the user out and remove data in a single flow.
    with transaction.atomic():
        user = request.user
        if has_analytics_consent(request):
            track_account_deleted_event(user.profile)
        logout(request)
        user.delete()

    logger.info(
        "account.deletion.completed",
        extra={
            "event.name": "account.deletion.completed",
            "user_id": user_id,
            "outcome": "success",
        },
    )
    return redirect(f"{reverse('landing')}?account_deleted=1")


@login_required
@require_POST
def create_checkout_session(request):
    user = request.user
    profile = user.profile
    price_id = settings.STRIPE_PRICE_ID_MONTHLY
    if not price_id:
        logger.warning(
            "stripe.checkout.create.completed",
            extra={
                "event.name": "stripe.checkout.create.completed",
                "user_id": user.id,
                "profile_id": profile.id,
                "operation.status": "price_not_configured",
                "outcome": "failure",
            },
        )
        messages.error(request, "Unable to find pricing for the selected plan.")
        return redirect("pricing")

    if profile.has_active_subscription:
        return redirect("home")

    try:
        price = stripe.Price.retrieve(
            price_id, expand=["product"], stripe_context=settings.STRIPE_CONTEXT or None
        )
        validate_monthly_price(price)
        customer = get_or_create_stripe_customer(profile, user)
    except (stripe.error.StripeError, ImproperlyConfigured) as exc:
        logger.error(
            "stripe.customer.ensure.completed",
            extra={
                "event.name": "stripe.customer.ensure.completed",
                "profile_id": profile.id,
                "outcome": "failure",
                "error.type": exc.__class__.__name__,
            },
            exc_info=True,
        )
        messages.error(request, "Unable to start checkout. Please try again.")
        return redirect("pricing")

    base_success_url = request.build_absolute_uri(reverse("home"))
    base_cancel_url = request.build_absolute_uri(reverse("home"))

    success_params = {"payment": "success"}
    success_url = f"{base_success_url}?{urlencode(success_params)}"

    cancel_params = {"payment": "failed"}
    cancel_url = f"{base_cancel_url}?{urlencode(cancel_params)}"

    session_params = {
        "customer": customer.id,
        "payment_method_types": ["card"],
        "automatic_tax": {"enabled": True},
        "line_items": [
            {
                "price": price_id,
                "quantity": 1,
            }
        ],
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "customer_update": {
            "address": "auto",
        },
        "client_reference_id": str(user.id),
        "metadata": {
            "user_id": user.id,
            "profile_id": profile.id,
            "price_id": price_id,
            "plan": MONTHLY_PRICE.plan,
        },
        "subscription_data": {
            "metadata": {
                "user_id": user.id,
                "profile_id": profile.id,
                "price_id": price_id,
                "plan": MONTHLY_PRICE.plan,
            }
        },
    }

    try:
        idempotency_key = request.session.setdefault(
            "stripe_checkout_idempotency_key", uuid.uuid4().hex
        )
        checkout_session = stripe.checkout.Session.create(
            **session_params,
            idempotency_key=f"citeguild-checkout-{profile.id}-{idempotency_key}",
            stripe_context=settings.STRIPE_CONTEXT or None,
        )
    except stripe.error.StripeError as exc:
        logger.error(
            "stripe.checkout.create.completed",
            extra={
                "event.name": "stripe.checkout.create.completed",
                "profile_id": profile.id,
                "plan": MONTHLY_PRICE.plan,
                "outcome": "failure",
                "error.type": exc.__class__.__name__,
            },
            exc_info=True,
        )
        messages.error(request, "Unable to start checkout. Please try again.")
        return redirect("pricing")

    if has_analytics_consent(request):
        track_event(
            profile,
            CHECKOUT_STARTED,
            {"plan": MONTHLY_PRICE.plan, "checkout_mode": "subscription"},
            source_function="create_checkout_session",
        )
    return HttpResponse(status=303, headers={"Location": checkout_session.url})


@login_required
@require_POST
def create_customer_portal_session(request):
    user = request.user
    profile = user.profile
    if not profile.stripe_customer_id:
        messages.error(request, "No Stripe customer found for this account.")
        return redirect("pricing")

    try:
        session = stripe.billing_portal.Session.create(
            customer=profile.stripe_customer_id,
            return_url=request.build_absolute_uri(reverse("home")),
            stripe_context=settings.STRIPE_CONTEXT or None,
        )
    except stripe.error.StripeError as exc:
        logger.error(
            "stripe.portal.create.completed",
            extra={
                "event.name": "stripe.portal.create.completed",
                "profile_id": profile.id,
                "stripe_customer_id": profile.stripe_customer_id,
                "outcome": "failure",
                "error.type": exc.__class__.__name__,
            },
            exc_info=True,
        )
        messages.error(request, "Unable to open the billing portal. Please try again.")
        return redirect("pricing")

    return HttpResponse(status=303, headers={"Location": session.url})


class AdminPanelView(UserPassesTestMixin, TemplateView):
    template_name = "pages/admin-panel.html"
    login_url = "account_login"

    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        messages.error(self.request, "You don't have permission to access this page.")
        return redirect("home")

    def get_context_data(self, **kwargs):
        from datetime import timedelta

        from django.contrib.auth.models import User
        from django.utils import timezone

        from apps.core.models import Profile

        context = super().get_context_data(**kwargs)

        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        total_users = User.objects.count()
        total_profiles = Profile.objects.count()

        new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
        new_users_month = User.objects.filter(date_joined__gte=month_ago).count()

        recent_users = User.objects.select_related("profile").order_by("-date_joined")[:10]

        # Calculate average users per day for last 30 days
        avg_users_per_day = new_users_month / 30 if new_users_month > 0 else 0

        context.update(
            {
                "total_users": total_users,
                "total_profiles": total_profiles,
                "new_users_week": new_users_week,
                "new_users_month": new_users_month,
                "recent_users": recent_users,
                "avg_users_per_day": avg_users_per_day,
            }
        )

        logger.info(
            "admin_panel.view.completed",
            extra={
                "event.name": "admin_panel.view.completed",
                "user_id": self.request.user.id,
                "profile_id": self.request.user.profile.id,
                "outcome": "success",
            },
        )

        return context


def get_or_create_stripe_customer(profile, user):
    if profile.stripe_customer_id:
        try:
            return stripe.Customer.retrieve(
                profile.stripe_customer_id, stripe_context=settings.STRIPE_CONTEXT or None
            )
        except stripe.error.InvalidRequestError as exc:
            logger.warning(
                "stripe.customer.lookup.completed",
                extra={
                    "event.name": "stripe.customer.lookup.completed",
                    "profile_id": profile.id,
                    "stripe_customer_id": profile.stripe_customer_id,
                    "outcome": "failure",
                    "error.type": exc.__class__.__name__,
                },
            )

    customer = stripe.Customer.create(
        email=user.email,
        name=user.get_full_name() or user.username,
        metadata={"user_id": user.id},
        idempotency_key=f"citeguild-customer-{profile.id}",
        stripe_context=settings.STRIPE_CONTEXT or None,
    )
    profile.stripe_customer_id = customer.id
    profile.save(update_fields=["stripe_customer_id"])
    return customer


def construct_stripe_event(request):
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    if not sig_header:
        logger.warning(
            "stripe.webhook.process.completed",
            extra={
                "event.name": "stripe.webhook.process.completed",
                "operation.status": "signature_missing",
                "outcome": "failure",
            },
        )
        return None, HttpResponseBadRequest("Missing Stripe-Signature header")

    try:
        event = stripe.Webhook.construct_event(
            payload=request.body,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
        if hasattr(event, "to_dict"):
            event = event.to_dict()
        return event, None
    except ValueError:
        logger.warning(
            "stripe.webhook.process.completed",
            extra={
                "event.name": "stripe.webhook.process.completed",
                "operation.status": "payload_invalid",
                "outcome": "failure",
                "error.type": "ValueError",
            },
        )
        return None, HttpResponseBadRequest("Invalid payload")
    except stripe.error.SignatureVerificationError:
        logger.warning(
            "stripe.webhook.process.completed",
            extra={
                "event.name": "stripe.webhook.process.completed",
                "operation.status": "signature_invalid",
                "outcome": "failure",
                "error.type": "SignatureVerificationError",
            },
        )
        return None, HttpResponseBadRequest("Invalid signature")


@csrf_exempt
def stripe_webhook(request):
    if request.method != "POST":
        return HttpResponse(status=405)

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error(
            "stripe.webhook.process.completed",
            extra={
                "event.name": "stripe.webhook.process.completed",
                "operation.status": "not_configured",
                "outcome": "failure",
            },
        )
        return HttpResponse(status=500)

    event, error_response = construct_stripe_event(request)
    if error_response is not None:
        return error_response

    event_id = event.get("id")
    if not event_id:
        return HttpResponseBadRequest("Missing event id")

    with transaction.atomic():
        _, created = StripeWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "event_type": event.get("type") or "",
                "event_created": int(event.get("created") or 0),
            },
        )
        if not created:
            return HttpResponse(status=200)

        handler = EVENT_HANDLERS.get(event.get("type"))
        if handler:
            handler(event)
        else:
            logger.info(
                "stripe.webhook.process.completed",
                extra={
                    "event.name": "stripe.webhook.process.completed",
                    "event_type": event.get("type"),
                    "event_id": event_id,
                    "operation.status": "unhandled",
                    "outcome": "success",
                },
            )

    if handler:
        logger.info(
            "stripe.webhook.process.completed",
            extra={
                "event.name": "stripe.webhook.process.completed",
                "event_type": event.get("type"),
                "event_id": event_id,
                "operation.status": "handled",
                "outcome": "success",
            },
        )

    return HttpResponse(status=200)
