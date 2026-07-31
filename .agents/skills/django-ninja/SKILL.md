---
name: django-ninja
description: "Use when adding, changing, testing, or debugging Django Ninja API endpoints, schemas, routers, authentication, OpenAPI docs, or API tests in this generated Django SaaS app."
---

# Django Ninja APIs

Use this before touching `apps/api/`, adding API endpoints, changing API
authentication, or debugging generated API behavior.

## Project Defaults

- `apps/api/views.py` owns the central `api = NinjaAPI()` instance.
- `apps/api/urls.py` mounts `api.urls` at `/api/`.
- `apps/api/schemas.py` contains request and response `Schema` classes.
- `apps/api/services.py` contains reusable serialization/business helpers.
- `apps/api/auth.py` contains API-key, bearer-token, session, and superuser
  authenticators.
- `apps/api/tests.py` contains API unit and integration coverage.
- `request.auth` is normally an `apps.core.models.Profile` for authenticated
  endpoints.

## Adding Endpoints

1. Add request and response schemas first. Prefer explicit `In`, `UpdateIn`,
   `Out`, `ListOut`, and `ErrorOut` classes over ad hoc dictionaries.
2. Put reusable serialization or business logic in `apps/api/services.py` or the
   owning app's service layer. Keep Ninja operation functions thin.
3. Decorate operations with an explicit method, path, `response=...`, `auth=...`,
   and `tags=[...]`.
4. Return `(status_code, payload)` whenever the operation declares multiple
   response schemas, for example `response={200: ItemOut, 404: ErrorOut}`.
5. Use `include_in_schema=False` for private, internal, healthcheck, or
   same-site endpoints that should not appear in public API docs.
6. Add tests for success, validation errors, auth failures, and any branch that
   returns a non-200 status.

## Schemas and Serialization

- Use `ninja.Schema` for request bodies and responses. It is backed by
  Pydantic, so standard Python type hints drive parsing, validation, and docs.
- For `PATCH` inputs, optional fields with `None` work when `None` means "leave
  unchanged." If clients must clear nullable values, inspect
  `data.model_fields_set` instead of relying only on `is not None`.
- Be cautious with `ModelSchema`. If you use it, list `fields` explicitly; do
  not use `fields = "__all__"` for user, profile, billing, token, or admin
  objects.
- Never expose password hashes, API-key hashes/secrets, internal state,
  `is_superuser`, provider tokens, or billing identifiers unless the endpoint is
  intentionally scoped for that data.
- Return Django model instances, querysets, dictionaries, or schema instances
  only when the declared response schema safely limits the output.
- Use `select_related` and `prefetch_related` before returning querysets with
  nested schemas to avoid N+1 queries.

## Auth and Security

- Use `api_key_auth` for external user API endpoints. It accepts
  `X-API-Key` and `Authorization: Bearer`.
- Use `superuser_api_auth` for admin/internal automation endpoints.
- Use `session_auth` only for same-site authenticated browser interactions.
- Do not add query-string API keys. Keep tokens and API keys out of URLs, logs,
  responses, docs examples with concrete values, and tests committed with real
  secrets.
- Treat `request.auth` as the authorization subject. Check ownership before
  returning or mutating user-owned records.
- For session-authenticated mutations, verify CSRF behavior explicitly; Django
  Ninja's API-level defaults differ from normal Django form views.

## Routers and Structure

- Keep one central `NinjaAPI` instance. Do not create a second project-level API
  object for a feature.
- When an API area grows, split endpoints into `ninja.Router` modules and attach
  them to the central API with `api.add_router(...)`.
- Put app-owned API code close to the owning app only when it improves
  ownership; otherwise keep shared API surface in `apps/api/`.
- Use router-level `auth=...` for groups with the same authentication and
  operation-level `auth=None` only for explicit public exceptions.

## Errors and Status Codes

- Prefer declared error schemas plus `(status, payload)` for expected 400, 401,
  403, 404, and 409 outcomes.
- Use `raise HttpError(status_code, message)` for simple exceptional failures
  where a common response shape is acceptable.
- For reusable domain exceptions, register `@api.exception_handler(...)` on the
  central API and return `api.create_response(...)`.
- Do not catch broad exceptions unless you log useful context and return a
  deliberate error response without leaking internals.

## Async

- Use normal synchronous operations by default; they match Django ORM usage and
  the generated project deployment path.
- Use `async def` only for operations dominated by async-safe network or file
  I/O.
- Do not call synchronous ORM queries directly inside async operations. Use
  Django async ORM APIs or wrap sync ORM work with an appropriate sync-to-async
  boundary.

## Testing

- For pure serialization, service, and authorization logic, call functions
  directly with `HttpRequest` or lightweight test objects.
- For route behavior, schema validation, response serialization, and auth
  integration, use Django's test client or `ninja.testing.TestClient`.
- Check validation failures return 422 when request data is invalid.
- Use explicit fake API keys such as `ak_public.secret`; never commit real keys.

```python
from ninja.testing import TestClient

from apps.api.views import api


def test_user_requires_auth():
    client = TestClient(api)

    response = client.get("/user")

    assert response.status_code == 401
```

Useful checks:

```bash
uv run python manage.py check
uv run pytest apps/api/tests.py -q
```

## References

- Official docs: https://django-ninja.dev/
- Routers: https://django-ninja.dev/guides/routers/
- Authentication: https://django-ninja.dev/guides/authentication/
- Schemas and responses: https://django-ninja.dev/guides/response/
- Testing: https://django-ninja.dev/guides/testing/
- Upstream repo: https://github.com/vitalik/django-ninja
