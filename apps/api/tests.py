from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpRequest
from django.test import SimpleTestCase


class UserInfoApiUnitTests(SimpleTestCase):
    def test_get_user_info_returns_safe_profile_data(self):
        from apps.api.views import get_user_info

        user = SimpleNamespace(
            id=7,
            email="ada@example.com",
            username="ada",
            first_name="Ada",
            last_name="Lovelace",
            date_joined="2026-05-14T00:00:00Z",
            get_full_name=lambda: "Ada Lovelace",
        )
        profile = SimpleNamespace(
            id=11,
            user=user,
            state="signed_up",
            has_active_subscription=False,
        )
        request = HttpRequest()
        request.auth = profile

        response = get_user_info(request)

        assert response["email"] == "ada@example.com"
        assert response["full_name"] == "Ada Lovelace"
        assert response["profile"] == {
            "id": 11,
            "state": "signed_up",
            "has_active_subscription": False,
        }
        assert "key" not in response


def test_api_key_auth_returns_profile_for_valid_key():
    from apps.api.auth import APIKeyHeaderAuth, BearerAPIKeyAuth
    from apps.core.models import Profile

    api_key = "ak_public.secret"

    for auth_class in [APIKeyHeaderAuth, BearerAPIKeyAuth]:
        profile = SimpleNamespace(id=11, check_api_key=Mock(return_value=True))
        with patch("apps.api.auth.Profile.objects") as objects:
            objects.select_related.return_value.get.return_value = profile
            response = auth_class().authenticate(HttpRequest(), api_key)

        assert response is profile
        objects.select_related.assert_called_once_with("user")
        objects.select_related.return_value.get.assert_called_once_with(api_key_prefix="ak_public")
        profile.check_api_key.assert_called_once_with(api_key)

    with patch("apps.api.auth.Profile.objects") as objects:
        objects.select_related.return_value.get.side_effect = Profile.DoesNotExist
        response = APIKeyHeaderAuth().authenticate(HttpRequest(), "ak_missing.secret")

    assert response is None

    with patch("apps.api.auth.Profile.objects") as objects:
        response = APIKeyHeaderAuth().authenticate(HttpRequest(), "bad-key")

    assert response is None
    objects.select_related.assert_not_called()


def test_superuser_api_key_auth_eager_loads_user_and_requires_superuser():
    from apps.api.auth import SuperuserAPIKeyHeaderAuth, SuperuserBearerAPIKeyAuth
    from apps.core.models import Profile

    api_key = "ak_public.secret"

    for auth_class in [SuperuserAPIKeyHeaderAuth, SuperuserBearerAPIKeyAuth]:
        superuser_profile = SimpleNamespace(
            id=11,
            user=SimpleNamespace(id=21, is_superuser=True),
            check_api_key=Mock(return_value=True),
        )
        regular_profile = SimpleNamespace(
            id=12,
            user=SimpleNamespace(id=22, is_superuser=False),
            check_api_key=Mock(return_value=True),
        )

        with patch("apps.api.auth.Profile.objects") as objects:
            objects.select_related.return_value.get.return_value = superuser_profile
            response = auth_class().authenticate(HttpRequest(), api_key)

        assert response is superuser_profile
        objects.select_related.assert_called_once_with("user")
        objects.select_related.return_value.get.assert_called_once_with(api_key_prefix="ak_public")
        superuser_profile.check_api_key.assert_called_once_with(api_key)

        with patch("apps.api.auth.Profile.objects") as objects:
            objects.select_related.return_value.get.return_value = regular_profile
            response = auth_class().authenticate(HttpRequest(), api_key)

        assert response is None
        regular_profile.check_api_key.assert_called_once_with(api_key)

        with patch("apps.api.auth.Profile.objects") as objects:
            objects.select_related.return_value.get.side_effect = Profile.DoesNotExist
            response = auth_class().authenticate(HttpRequest(), "ak_missing.secret")

        assert response is None
