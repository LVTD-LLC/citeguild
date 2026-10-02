"""Exercise the real allauth login stage without a physical browser authenticator."""

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db
PASSWORD = "test-only-strong-password-123"


@pytest.fixture
def member():
    user = get_user_model().objects.create_user(
        username="mfa-member", email="mfa-member@example.com", password=PASSWORD
    )
    EmailAddress.objects.update_or_create(
        user=user, email=user.email, defaults={"primary": True, "verified": True}
    )
    return user


@pytest.fixture
def passkey_member(member, monkeypatch):
    Authenticator.objects.create(
        user=member, type=Authenticator.Type.WEBAUTHN, data={"name": "Test passkey"}
    )
    # Only physical credential extraction is stubbed. Login stages, request options,
    # sessions, CSRF, code validation and recovery consumption remain real.
    monkeypatch.setattr("allauth.mfa.webauthn.internal.auth.get_credentials", lambda user: [])
    RecoveryCodes.activate(member)
    return member


def start_login(client, member):
    return client.post(reverse("account_login"), {"login": member.email, "password": PASSWORD})


def test_password_login_without_passkey_does_not_require_mfa(client, member):
    response = start_login(client, member)
    assert response.status_code == 302
    assert response.url == reverse("home")
    assert client.session["_auth_user_id"] == str(member.pk)


def test_passkey_login_stage_is_styled_and_describes_recovery(client, passkey_member):
    response = start_login(client, passkey_member)
    assert response.url == reverse("mfa_authenticate")
    assert "_auth_user_id" not in client.session
    response = client.get(response.url)
    content = response.content.decode()
    assert response.status_code == 200
    assert "css/app.css" in content
    assert "Verify your sign-in" in content
    assert "Use your passkey" in content
    assert "Recovery code" in content
    assert "authenticator code" not in content
    assert "Passkeys are tied to the domain" in content
    assert 'id="mfa_webauthn_authenticate"' in content
    assert 'name="credential"' in content
    assert "allauth.webauthn.forms.authenticateForm" in content
    assert "mfa/js/webauthn.js" in content
    assert "noindex, nofollow" in content


def test_invalid_recovery_code_keeps_login_blocked(client, passkey_member):
    start_login(client, passkey_member)
    response = client.post(reverse("mfa_authenticate"), {"code": "invalid-code"})
    assert response.status_code == 200
    assert response.context["form"].errors["code"]
    assert "css/app.css" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_recovery_code_completes_login_and_cannot_be_reused(client, passkey_member):
    recovery = Authenticator.objects.get(
        user=passkey_member, type=Authenticator.Type.RECOVERY_CODES
    )
    code = recovery.wrap().get_unused_codes()[0]
    start_login(client, passkey_member)
    response = client.post(reverse("mfa_authenticate"), {"code": code})
    assert response.status_code == 302
    assert response.url == reverse("home")
    assert client.session["_auth_user_id"] == str(passkey_member.pk)
    client.logout()
    start_login(client, passkey_member)
    response = client.post(reverse("mfa_authenticate"), {"code": code})
    assert response.status_code == 200
    assert response.context["form"].errors["code"]
    assert "_auth_user_id" not in client.session


def test_cancel_abandons_mfa_stage(client, passkey_member):
    start_login(client, passkey_member)
    response = client.post(reverse("account_logout"), {"next": reverse("account_login")})
    assert response.url == reverse("account_login")
    assert "_auth_user_id" not in client.session
    assert client.get(reverse("mfa_authenticate")).url == reverse("account_login")


def test_mfa_post_requires_csrf(client, passkey_member):
    start_login(client, passkey_member)
    protected = Client(enforce_csrf_checks=True)
    protected.cookies = client.cookies
    assert protected.post(reverse("mfa_authenticate"), {"code": "123456"}).status_code == 403
    assert "_auth_user_id" not in protected.session
