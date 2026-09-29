"""Invitation validation shared by password, passkey, and social signup."""

from uuid import UUID

from django.core.exceptions import PermissionDenied

from apps.core.models import MemberInvitation

INVITATION_SESSION_KEY = "signup_invitation"


def valid_invitation(code):
    try:
        code = UUID(str(code).strip())
    except (ValueError, TypeError, AttributeError):
        return None
    return MemberInvitation.objects.filter(code=code, owner__user__is_active=True).first()


def request_invitation(request):
    code = request.POST.get("invitation_code")
    if code is None:
        code = getattr(request, "session", {}).get(INVITATION_SESSION_KEY)
    return valid_invitation(code)


def require_invitation(request):
    from django.conf import settings

    if not getattr(settings, "ALLOW_SIGNUPS", True) or not request_invitation(request):
        raise PermissionDenied("A valid invitation is required to register.")
