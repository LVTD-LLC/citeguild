# Frontend

This project uses Django templates as the primary UI layer, with a small static
asset build:

- Tailwind CSS is compiled from `frontend/src/styles/index.css` to
  `frontend/static/css/app.css`.
- HTMX and Alpine.js are copied from npm packages to
  `frontend/static/vendors/js/`.
- Browser modules are copied from `frontend/src/js/` to `frontend/static/js/`.
- Keyboard shortcuts live in `frontend/src/js/modules/shortcuts.js` and are
  registered from `data-shortcut-key` attributes on rendered controls.


## Scripts

```bash
npm ci
npm run build
npm run watch
npm run lint
```

`npm run build` prepares production static assets before `collectstatic`.
`npm run watch` keeps Tailwind CSS rebuilding during local development.

## Frontend Rules

- Use Django templates first.
- Use HTMX when an action needs fresh server-rendered HTML.
- Use Alpine.js when state is local to the browser, such as dropdowns, modals,
  and toggles.
- Keep keyboard shortcut hints desktop-only with `.shortcut-kbd` plus responsive
  visibility utilities.
- Keep normal Django forms and server validation as the source of truth.
- Do not add a JavaScript bundler unless the product intentionally adopts a
  different frontend architecture.
