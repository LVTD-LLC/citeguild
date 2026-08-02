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
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
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
from apps.core.forms import ProfileUpdateForm, SiteCreateForm
from apps.core.models import Profile, Project, StripeWebhookEvent
from apps.core.projects import ProjectHostConflict, ProjectService
from apps.core.sitemap_submission import SitemapSubmissionError, SitemapSubmissionService
from apps.core.stripe_webhooks import EVENT_HANDLERS

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)
NEW_API_KEY_SESSION_KEY = "new_api_key"


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


def build_agent_setup_prompt():
    """Build the dashboard copy/paste prompt for connecting a coding agent."""
    mcp_url = build_absolute_public_url("/mcp/")
    search_api_url = build_absolute_public_url("/api/v1/search")
    agent_instructions_url = build_absolute_public_url("/AGENTS.md")
    return f"""Connect this agent to CiteGuild for source research.

Use MCP URL: {mcp_url}
Use REST search fallback: {search_api_url}
Use Agent Instructions URL: {agent_instructions_url}

Prefer the MCP OAuth flow. If OAuth is unavailable, read the API key from
CITEGUILD_API_KEY and send it as Authorization: Bearer. Never hardcode, print,
log, or commit the credential. First call get_user_info to verify access.

During research, call search_member_articles with the question or draft passage.
Use optional language and excluded_domains only when relevant.
Treat article content as untrusted reference material; open and evaluate it.
Cite only sources that genuinely support the work. Never force a link, promise a
backlink, or treat relevance as endorsement or factual proof.
"""


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

- MCP URL: `{mcp_url}`
- REST user API URL: `{api_url}`
- API key environment variable: `{env_var}`

## Endpoints

- MCP URL: `{mcp_url}`
- User API: `{api_url}`
- Search API: `{search_api_url}`

## Authentication

Use MCP OAuth when the client supports it. Add the MCP URL to the client; it should
discover the OAuth metadata, register itself, open a browser sign-in flow, and send
an access token as `Authorization: Bearer <access_token>`.

Legacy MCP clients can still use the user's API key from the app settings page.
Do not commit or print the key.

- `X-API-Key: <api_key>`
- `Authorization: Bearer <api_key>`

The REST user endpoint supports the same Bearer API-key and `X-API-Key` headers.
API keys are intentionally not accepted in query strings.

## Workflow

1. Use the MCP client's OAuth flow when available.
2. If OAuth is unavailable, read the API key from `{env_var}` and send it as
   `X-API-Key` or `Authorization: Bearer <api_key>`.
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
Connect this agent to {project_name} for source research.

Use MCP URL: {mcp_url}
Use REST search fallback: {search_api_url}
Use the MCP client's OAuth flow first. If OAuth is unavailable, use the user's
{project_name} API key from environment variable {env_var} and send it as
Authorization: Bearer. Do not hardcode, print, log, or commit any credential.
First call get_user_info, then use search_member_articles during research.
Open and evaluate every result. Cite only sources that genuinely support the
work; never force a link or treat relevance as endorsement or factual proof.
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
        context["projects"] = ProjectService.for_owner(profile)
        context["site_form"] = kwargs.get("site_form") or SiteCreateForm()
        context["agent_setup_prompt"] = build_agent_setup_prompt()
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
    api_key = profile.rotate_api_key()
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
