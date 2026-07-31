import pytest
from hypothesis import given
from hypothesis import strategies as st

from apps.core.model_utils import (
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
    verify_api_key,
)


@given(api_key=st.text(min_size=1))
def test_api_key_hash_round_trips_arbitrary_text(api_key):
    api_key_hash = hash_api_key(api_key)

    assert verify_api_key(api_key, api_key_hash)
    assert not verify_api_key(f"{api_key}\0", api_key_hash)


def test_generate_api_key_uses_secrets_token_urlsafe(monkeypatch):
    calls = []

    def fake_token_urlsafe(byte_count):
        calls.append(byte_count)
        return f"token_{byte_count}_{len(calls)}"

    monkeypatch.setattr("apps.core.model_utils.secrets.token_urlsafe", fake_token_urlsafe)

    api_key = generate_api_key()

    assert api_key == "ak_token_12_1.token_32_2"
    assert calls == [12, 32]
    assert get_api_key_prefix(api_key) == "ak_token_12_1"


def test_get_api_key_prefix_requires_public_part_and_secret():
    assert get_api_key_prefix("ak_public.secret") == "ak_public"
    assert get_api_key_prefix("ak_public.") == ""
    assert get_api_key_prefix("ak_public") == ""
    assert get_api_key_prefix("public.secret") == ""


def test_api_key_hash_uses_per_key_salt():
    api_key = "ak_public.secret"

    first_hash = hash_api_key(api_key)
    second_hash = hash_api_key(api_key)
    version, salt, digest = first_hash.split("$", 2)

    assert first_hash != api_key
    assert first_hash != second_hash
    assert version == "v1"
    assert salt
    assert len(digest) == 64
    assert verify_api_key(api_key, first_hash)
    assert verify_api_key(api_key, second_hash)
    assert not verify_api_key("ak_public.other-secret", first_hash)
    assert not verify_api_key(api_key, "v1$$bad-digest")
    assert not verify_api_key(api_key, "bad-format")


@pytest.mark.django_db
def test_profile_api_key_is_hashed_and_verifiable(profile):
    api_key = profile.rotate_api_key()
    profile.refresh_from_db()

    assert profile.api_key_prefix == get_api_key_prefix(api_key)
    assert api_key not in profile.api_key_hash
    assert profile.check_api_key(api_key)
    assert not profile.check_api_key("ak_missing.secret")
