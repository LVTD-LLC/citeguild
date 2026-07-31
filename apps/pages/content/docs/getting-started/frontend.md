---
title: Frontend
description: Django-native frontend conventions for templates, HTMX, Alpine.js, and Tailwind CSS.
---

# Frontend

CiteGuild keeps the frontend close to Django.

## Asset build

The generated app uses a small static asset build:

- `frontend/src/styles/index.css` is the Tailwind CSS input.
- `frontend/static/css/app.css` is the compiled CSS served by Django staticfiles.
- `frontend/src/js/` contains small browser modules.
- `frontend/static/js/` contains the copied browser modules served by Django.
- `frontend/static/vendors/js/` contains npm-managed HTMX and Alpine.js files.
- `frontend/src/js/modules/shortcuts.js` registers keyboard shortcuts from
  rendered `data-shortcut-key` controls.


The browser modules are copied as individual files so they stay easy to inspect and debug in a generated Django project. Add bundling later only if your app needs it.

Build assets before production `collectstatic`:

```bash
npm ci
npm run build
uv run python manage.py collectstatic --noinput
```

During local template, style, and JavaScript work, run:

```bash
npm run watch
```

## Interactivity rules

Use Django templates first. Reach for JavaScript only when the interaction needs it.

Use HTMX when an action needs fresh server-rendered HTML from Django. A view that returns different content for HTMX requests should vary on `HX-Request`.

```python
from django.shortcuts import render
from django.utils.cache import patch_vary_headers


def customer_list(request):
    template_name = (
        "pages/customers/partials/customer_table.html"
        if request.htmx
        else "pages/customers/list.html"
    )

    response = render(request, template_name, {"customers": customers})
    patch_vary_headers(response, ["HX-Request"])
    return response
```

The full page should include the same partial that the HTMX response returns so
direct loads and refreshes render the same server-owned UI.

Use Alpine.js when the state is local to the browser, such as dropdowns, modals, disclosure panels, and theme toggles.

Keyboard shortcuts should stay tied to visible navigation controls. Use one stable letter per action, ignore text-entry fields, and keep shortcut hints hidden below large desktop breakpoints.

Keep normal Django forms and server validation as the source of truth. Avoid JSON for ordinary page updates unless you are integrating a third-party widget or background behavior.

## UI quality workflow

Before changing generated UI, read:

- `DESIGN.md`
- `.agents/skills/frontend-ui-quality/SKILL.md`

Keep repeated Tailwind patterns in `frontend/src/styles/index.css`, not copied across templates. Verify light mode, dark mode, mobile layout, desktop layout, focus-visible states, empty states, errors, disabled controls, and reduced-motion behavior before shipping.
