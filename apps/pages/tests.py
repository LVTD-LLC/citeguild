import time

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.urls import reverse

pytestmark = pytest.mark.django_db


def mark_password_reauthenticated(client, username):
    session = client.session
    session["account_authentication_methods"] = [
        {"method": "password", "at": time.time(), "username": username}
    ]
    session.save()


def test_login_page_shows_passkey_option(client):
    response = client.get(reverse("account_login"))
    assert response.status_code == 200

    content = response.content.decode()
    assert "Sign in with a passkey" in content
    assert 'id="mfa_login"' in content
    assert "window.webauthnJSON.get(requestOptions)" in content
    assert "X-Requested-With" in content
    assert "allauth.webauthn.forms.loginForm" not in content


def test_signup_page_shows_passkey_signup_option(client):
    response = client.get(reverse("account_signup"))
    assert response.status_code == 200

    content = response.content.decode()
    assert "Username" not in content
    assert "Confirm Password" not in content
    assert "Cofirm Password" not in content
    assert "Sign up using a passkey" in content
    assert reverse("account_signup_by_passkey") in content


def test_passkey_signup_page_uses_app_styling(client):
    response = client.get(reverse("account_signup_by_passkey"))
    assert response.status_code == 200

    content = response.content.decode()
    assert "Create your account with a passkey" in content
    assert "Password" not in content
    assert "Continue with passkey" in content
    assert "Menu:" not in content


def test_login_page_uses_email_instead_of_username(client):
    response = client.get(reverse("account_login"))
    assert response.status_code == 200

    content = response.content.decode()
    assert 'placeholder="Email"' in content
    assert 'type="email"' in content
    assert 'placeholder="Username"' not in content


def test_signup_redirects_to_email_code_verification(client, monkeypatch, settings):
    sent_confirmations = []

    def fake_send_confirmation_mail(self, request, emailconfirmation, signup):
        sent_confirmations.append((emailconfirmation.email_address.email, signup))

    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail",
        fake_send_confirmation_mail,
    )
    settings.POSTHOG_API_KEY = ""

    response = client.post(
        reverse("account_signup"),
        data={
            "email": "newuser@example.com",
            "password1": "strong-test-pass-123",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("account_email_verification_sent")
    user = get_user_model().objects.get(email="newuser@example.com")
    assert user.username
    assert sent_confirmations == [("newuser@example.com", True)]
    verification = client.session["account_email_verification_code"]
    assert verification["email"] == "newuser@example.com"
    assert verification["code"]


def test_email_verification_code_page_uses_app_styling(client, monkeypatch, settings):
    def fake_send_confirmation_mail(self, request, emailconfirmation, signup):
        pass

    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail",
        fake_send_confirmation_mail,
    )
    settings.POSTHOG_API_KEY = ""

    client.post(
        reverse("account_signup"),
        data={
            "email": "codeuser@example.com",
            "password1": "strong-test-pass-123",
        },
    )

    response = client.get(reverse("account_email_verification_sent"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Enter email verification code" in content
    assert 'autocomplete="one-time-code"' in content
    assert "Menu:" not in content


def test_passkey_signup_verifies_email_then_shows_styled_passkey_creation(
    client, monkeypatch, settings
):
    def fake_send_confirmation_mail(self, request, emailconfirmation, signup):
        pass

    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail",
        fake_send_confirmation_mail,
    )
    settings.POSTHOG_API_KEY = ""

    signup_response = client.post(
        reverse("account_signup_by_passkey"),
        data={"email": "passkey-new@example.com"},
    )
    assert signup_response.status_code == 302
    assert signup_response["Location"] == reverse("account_email_verification_sent")

    code = client.session["account_email_verification_code"]["code"]
    verify_response = client.post(
        reverse("account_email_verification_sent"),
        data={"code": code},
    )

    assert verify_response.status_code == 302
    assert verify_response["Location"] == reverse("mfa_signup_webauthn")

    form_response = client.get(reverse("mfa_signup_webauthn"))
    assert form_response.status_code == 200
    content = form_response.content.decode()
    assert "Create your passkey" in content
    assert 'id="mfa_webauthn_signup"' in content
    assert "allauth.webauthn.forms.signupForm" in content
    assert "Menu:" not in content


def test_dashboard_does_not_show_email_confirmation_reminder(client):
    user = get_user_model().objects.create_user(
        username="unverified",
        email="unverified@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": False},
    )
    client.force_login(user)

    response = client.get(reverse("home"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Your email is not yet confirmed" not in content
    assert "Your sites" in content


def test_settings_requires_email_confirmation_before_passkey_setup(client):
    user = get_user_model().objects.create_user(
        username="settingsuser",
        email="settingsuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": False},
    )
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Your email is not yet confirmed" in content
    assert "Confirm email to add passkey" in content
    assert "Add passkey" not in content
    assert reverse("mfa_add_webauthn") not in content


def test_settings_handles_users_without_allauth_email_address(client):
    user = get_user_model().objects.create_user(
        username="noemailaddress",
        email="noemailaddress@example.com",
        password="strong-test-pass-123",
    )
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Your email is not yet confirmed" in content
    assert "Confirm email to add passkey" in content
    assert "Add passkey" not in content
    assert reverse("mfa_add_webauthn") not in content


def test_settings_shows_passkey_setup_when_email_confirmed(client):
    user = get_user_model().objects.create_user(
        username="verifiedsettingsuser",
        email="verifiedsettingsuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Your email is not yet confirmed" not in content
    assert "Confirm email to add passkey" not in content
    assert "Add passkey" in content
    assert "Account email" in content
    assert reverse("mfa_add_webauthn") in content
    assert reverse("account_email") in content


def test_settings_shows_passkey_manage_link_when_passkey_exists(client):
    user = get_user_model().objects.create_user(
        username="passkeyuser",
        email="passkeyuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.WEBAUTHN,
        data={"name": "Test passkey"},
    )
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "You have 1 passkey set up." in content
    assert "Manage passkeys" in content
    assert "Generate recovery codes" in content
    assert reverse("mfa_list_webauthn") in content
    assert reverse("mfa_generate_recovery_codes") in content


def test_settings_links_to_existing_recovery_codes(client):
    user = get_user_model().objects.create_user(
        username="recoverysettingsuser",
        email="recoverysettingsuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.WEBAUTHN,
        data={"name": "Test passkey"},
    )
    RecoveryCodes.activate(user)
    client.force_login(user)

    response = client.get(reverse("settings"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "View recovery codes" in content
    assert reverse("mfa_view_recovery_codes") in content


def test_mfa_index_uses_app_styling(client):
    user = get_user_model().objects.create_user(
        username="mfauser",
        email="mfauser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    client.force_login(user)

    response = client.get(reverse("mfa_index"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Passkeys" in content
    assert "Add passkey" in content
    assert "Recovery codes" in content
    assert "Menu:" not in content


def test_mfa_index_links_to_recovery_code_generation_when_passkey_exists(client):
    user = get_user_model().objects.create_user(
        username="mfarecoveryuser",
        email="mfarecoveryuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.WEBAUTHN,
        data={"name": "Test passkey"},
    )
    client.force_login(user)

    response = client.get(reverse("mfa_index"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Generate codes" in content
    assert reverse("mfa_generate_recovery_codes") in content


def test_recovery_codes_generate_page_uses_app_styling_and_creates_codes(client):
    user = get_user_model().objects.create_user(
        username="generatecodesuser",
        email="generatecodesuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.WEBAUTHN,
        data={"name": "Test passkey"},
    )
    assert client.login(username="generatecodesuser", password="strong-test-pass-123")
    mark_password_reauthenticated(client, "generatecodesuser")

    response = client.get(reverse("mfa_generate_recovery_codes"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Generate recovery codes" in content
    assert "Recovery codes are the fallback for passkey-protected accounts." in content
    assert "Menu:" not in content

    response = client.post(reverse("mfa_generate_recovery_codes"))

    assert response.status_code == 302
    assert response["Location"] == reverse("mfa_view_recovery_codes")
    assert Authenticator.objects.filter(
        user=user,
        type=Authenticator.Type.RECOVERY_CODES,
    ).exists()


def test_recovery_codes_page_uses_app_styling(client):
    user = get_user_model().objects.create_user(
        username="viewcodesuser",
        email="viewcodesuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    RecoveryCodes.activate(user)
    assert client.login(username="viewcodesuser", password="strong-test-pass-123")
    mark_password_reauthenticated(client, "viewcodesuser")

    response = client.get(reverse("mfa_view_recovery_codes"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Recovery codes" in content
    assert "Download codes" in content
    assert "Generate new codes" in content
    assert reverse("mfa_download_recovery_codes") in content
    assert reverse("mfa_generate_recovery_codes") in content
    assert "Menu:" not in content


def test_recovery_codes_page_can_require_save_confirmation(client, settings):
    settings.MFA_RECOVERY_CODES_SHOW_ONCE = True
    user = get_user_model().objects.create_user(
        username="viewoncecodesuser",
        email="viewoncecodesuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    RecoveryCodes.activate(user)
    assert client.login(username="viewoncecodesuser", password="strong-test-pass-123")
    mark_password_reauthenticated(client, "viewoncecodesuser")

    response = client.get(reverse("mfa_view_recovery_codes"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "I have saved my recovery codes" in content
    assert "allauth.recoveryCodes.forms.viewForm" in content
    assert "Download codes" not in content


def test_webauthn_add_page_loads_styled_form_and_scripts(client):
    user = get_user_model().objects.create_user(
        username="addpasskeyuser",
        email="addpasskeyuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    assert client.login(username="addpasskeyuser", password="strong-test-pass-123")
    mark_password_reauthenticated(client, "addpasskeyuser")

    response = client.get(reverse("mfa_add_webauthn"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Add passkey" in content
    assert 'id="mfa_webauthn_add"' in content
    assert "allauth.webauthn.forms.addForm" in content
    assert "mfa/js/webauthn.js" in content
    assert "Menu:" not in content


def test_reauthenticate_page_uses_app_styling(client):
    user = get_user_model().objects.create_user(
        username="reauthuser",
        email="reauthuser@example.com",
        password="strong-test-pass-123",
    )
    client.force_login(user)

    response = client.get(reverse("account_reauthenticate"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Confirm access" in content
    assert "Menu:" not in content


def test_account_email_page_uses_app_styling(client):
    assert settings.ACCOUNT_CHANGE_EMAIL is True
    user = get_user_model().objects.create_user(
        username="emailpageuser",
        email="emailpageuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": True},
    )
    client.force_login(user)

    response = client.get(reverse("account_email"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Email address" in content
    assert "Current email" in content
    assert "Change Email" in content
    assert "Menu:" not in content


def test_social_connections_page_uses_app_styling(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {"github": {"APP": {"client_id": "x", "secret": "y"}}}
    user = get_user_model().objects.create_user(
        username="githubconnectionsuser",
        email="githubconnectionsuser@example.com",
        password="strong-test-pass-123",
    )
    SocialAccount.objects.create(
        user=user,
        provider="github",
        uid="12345",
        extra_data={"login": "octocat"},
    )
    client.force_login(user)

    response = client.get(reverse("socialaccount_connections"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Connected accounts" in content
    assert "octocat" in content
    assert "Remove selected account" in content
    assert "Remove this connected account?" in content
    assert "Add a third-party account" in content
    assert "Connect GitHub" in content
    assert "data-social-account-connections" in content
    assert "Menu:" not in content


def test_social_connections_page_shows_connect_cta_without_connected_account(client, settings):
    settings.SOCIALACCOUNT_PROVIDERS = {"github": {"APP": {"client_id": "x", "secret": "y"}}}
    user = get_user_model().objects.create_user(
        username="nogithubconnectionsuser",
        email="nogithubconnectionsuser@example.com",
        password="strong-test-pass-123",
    )
    client.force_login(user)

    response = client.get(reverse("socialaccount_connections"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "No third-party accounts are connected yet." in content
    assert "Connect GitHub" in content
    assert "Social auth unavailable" not in content
    assert "Remove selected account" not in content


def test_settings_resend_confirmation_uses_email_code(client, monkeypatch):
    sent_confirmations = []

    def fake_send_confirmation_mail(self, request, emailconfirmation, signup):
        sent_confirmations.append((emailconfirmation, signup))

    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail",
        fake_send_confirmation_mail,
    )
    user = get_user_model().objects.create_user(
        username="resenduser",
        email="resenduser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": False},
    )
    client.force_login(user)

    response = client.post(reverse("resend_confirmation"))

    assert response.status_code == 302
    assert response["Location"] == reverse("account_email_verification_sent")
    assert len(list(get_messages(response.wsgi_request))) == 1
    assert len(sent_confirmations) == 1
    emailconfirmation, signup = sent_confirmations[0]
    assert signup is False
    assert emailconfirmation.key == client.session["account_email_verification_code"]["code"]
    assert not EmailAddress.objects.get(user=user, email=user.email).verified


def test_settings_resend_confirmation_requires_post(client):
    user = get_user_model().objects.create_user(
        username="resendgetuser",
        email="resendgetuser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": False},
    )
    client.force_login(user)

    response = client.get(reverse("resend_confirmation"))

    assert response.status_code == 405


def test_settings_resend_confirmation_code_confirms_email(client, monkeypatch):
    sent_confirmations = []

    def fake_send_confirmation_mail(self, request, emailconfirmation, signup):
        sent_confirmations.append(emailconfirmation)

    monkeypatch.setattr(
        "citeguild.adapters.CustomAccountAdapter.send_confirmation_mail",
        fake_send_confirmation_mail,
    )
    user = get_user_model().objects.create_user(
        username="confirmresenduser",
        email="confirmresenduser@example.com",
        password="strong-test-pass-123",
    )
    EmailAddress.objects.update_or_create(
        user=user,
        email=user.email,
        defaults={"primary": True, "verified": False},
    )
    client.force_login(user)

    response = client.post(reverse("resend_confirmation"))

    assert response.status_code == 302
    assert len(sent_confirmations) == 1
    confirm_response = client.post(
        reverse("account_email_verification_sent"),
        data={"code": sent_confirmations[0].key},
    )

    assert confirm_response.status_code == 302
    assert EmailAddress.objects.get(user=user, email=user.email).verified is True


def test_mailgun_sender_defaults_are_configurable():
    expected_server_email = "CiteGuild Errors <error@citeguild.app>"

    assert settings.DEFAULT_FROM_EMAIL == "LVTD LLC from CiteGuild <hello@citeguild.app>"
    assert settings.SERVER_EMAIL == expected_server_email
    assert settings.ANYMAIL["MAILGUN_SENDER_DOMAIN"] == "mg.citeguild.app"
