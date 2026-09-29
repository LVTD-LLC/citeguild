import pytest
from django.contrib.auth.models import User
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def isolated_auth_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def test_registration_requires_invitation(client):
    response = client.post(
        reverse("account_signup"),
        {"email": "new@example.com", "password1": "A-secure-password-1928!"},
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="new@example.com").exists()
    assert "invitation_code" in response.context["form"].errors


def test_free_account_sees_sites_without_checkout(auth_client):
    response = auth_client.get(reverse("home"))
    assert response.status_code == 200
    assert "Add site" in response.content.decode()
    assert "Subscribe for" not in response.content.decode()


def test_new_checkout_is_disabled(auth_client, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Must not create a Stripe checkout")

    monkeypatch.setattr("stripe.checkout.Session.create", unexpected)
    response = auth_client.post(reverse("user_upgrade_checkout_session"))
    assert response.status_code == 302
    assert response.url == reverse("home")


@pytest.fixture
def invitation(profile):
    from apps.core.models import MemberInvitation

    return MemberInvitation.objects.create(owner=profile)


@pytest.mark.parametrize("route", ["account_signup", "account_signup_by_passkey"])
def test_invitation_accepts_password_and_passkey_signup(client, invitation, route, monkeypatch):
    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail", lambda *a, **kw: None
    )
    response = client.post(
        reverse(route),
        {
            "email": "invited@example.com",
            "password1": "A-secure-password-1928!",
            "invitation_code": str(invitation.code),
        },
    )
    assert response.status_code == 302
    assert User.objects.filter(email="invited@example.com").exists()
    assert response.url == reverse("account_email_verification_sent")


@pytest.mark.parametrize("code", ["", "not-a-code", "00000000-0000-0000-0000-000000000000"])
@pytest.mark.parametrize("route", ["account_signup", "account_signup_by_passkey"])
def test_invalid_invitation_creates_no_account(client, code, route):
    response = client.post(
        reverse(route),
        {
            "email": "invalid@example.com",
            "password1": "A-secure-password-1928!",
            "invitation_code": code,
        },
    )
    assert response.status_code == 200
    assert "&lt;div" not in response.content.decode()
    assert not User.objects.filter(email="invalid@example.com").exists()


def test_invite_link_survives_switch_to_passkey(client, invitation):
    response = client.get(reverse("account_signup"), {"invite": str(invitation.code)})
    assert response.context["form"]["invitation_code"].value() == str(invitation.code)
    response = client.get(reverse("account_signup_by_passkey"))
    assert response.context["form"]["invitation_code"].value() == str(invitation.code)
    response = client.get(reverse("account_signup"), {"invite": "invalid"})
    assert response.context["form"]["invitation_code"].value() == ""


def test_disabled_inviter_code_is_rejected(client, invitation):
    inviter = invitation.owner.user
    inviter.is_active = False
    inviter.save(update_fields=["is_active"])
    response = client.post(
        reverse("account_signup"),
        {
            "email": "invalid@example.com",
            "password1": "A-secure-password-1928!",
            "invitation_code": str(invitation.code),
        },
    )
    assert response.status_code == 200
    assert "&lt;div" not in response.content.decode()
    assert not User.objects.filter(email="invalid@example.com").exists()


def test_settings_invite_is_stable_and_owner_scoped(auth_client, profile, django_user_model):
    from apps.core.models import MemberInvitation

    other = django_user_model.objects.create_user(username="other", email="other@example.com")
    other_invite = MemberInvitation.objects.create(owner=other.profile)
    first = auth_client.get(reverse("settings"))
    second = auth_client.get(reverse("settings"))
    code = first.context["invitation_code"]
    assert code == second.context["invitation_code"]
    assert code != str(other_invite.code)
    assert MemberInvitation.objects.get(owner=profile).code.hex == code.replace("-", "")
    assert f"?invite={code}" in first.context["invitation_url"]
    assert str(other_invite.code) not in first.content.decode()
    assert 'data-copy-source="#invitation-url"' in first.content.decode()


def test_social_auto_signup_requires_invitation(rf, invitation):
    from citeguild.adapters import CustomSocialAccountAdapter

    request = rf.get("/accounts/github/login/callback/")
    request.session = {}
    adapter = CustomSocialAccountAdapter()
    assert adapter.is_open_for_signup(request, None) is False
    request.session["signup_invitation"] = str(invitation.code)
    assert adapter.is_open_for_signup(request, None) is True


def test_adapter_persistence_cannot_bypass_invite(rf):
    from django.core.exceptions import PermissionDenied

    from citeguild.adapters import CustomAccountAdapter, CustomSocialAccountAdapter

    request = rf.post("/accounts/signup/", {})
    request.session = {}
    with pytest.raises(PermissionDenied):
        CustomAccountAdapter().save_user(request, User(), None)
    with pytest.raises(PermissionDenied):
        CustomSocialAccountAdapter().save_user(request, None)


def test_pause_overrides_valid_invitation(client, invitation, settings):
    settings.ALLOW_SIGNUPS = False
    response = client.post(
        reverse("account_signup"),
        {
            "email": "paused@example.com",
            "password1": "A-secure-password-1928!",
            "invitation_code": str(invitation.code),
        },
    )
    assert not User.objects.filter(email="paused@example.com").exists()
    assert "Signups paused" in response.content.decode()


@pytest.mark.parametrize("header", ["HTTP_X_API_KEY", "HTTP_AUTHORIZATION"])
def test_disabled_account_api_key_is_rejected(client, profile, header):
    key = profile.rotate_api_key()
    profile.user.is_active = False
    profile.user.save(update_fields=["is_active"])
    credential = f"Bearer {key}" if header == "HTTP_AUTHORIZATION" else key
    assert client.get("/api/v1/account", **{header: credential}).status_code == 401


def test_invitation_can_be_reused(client, invitation, monkeypatch):
    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail", lambda *a, **kw: None
    )
    for number in range(2):
        response = client.post(
            reverse("account_signup"),
            {
                "email": f"invited-{number}@example.com",
                "password1": "A-secure-password-1928!",
                "invitation_code": str(invitation.code),
            },
        )
        assert response.status_code == 302
        assert User.objects.filter(email=f"invited-{number}@example.com").exists()
        client.logout()


def test_existing_email_signup_with_invite_is_handled_without_duplicate(
    client, invitation, monkeypatch
):
    monkeypatch.setattr("citeguild.adapters.CustomAccountAdapter.send_mail", lambda *a, **kw: None)
    email = invitation.owner.user.email
    before = User.objects.filter(email=email).count()
    response = client.post(
        reverse("account_signup"),
        {
            "email": email,
            "password1": "A-secure-password-1928!",
            "invitation_code": str(invitation.code),
        },
    )
    assert response.status_code in {200, 302}
    assert User.objects.filter(email=email).count() == before
