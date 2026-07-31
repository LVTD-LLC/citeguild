---
name: frontend-ui-quality
description: Use when changing Django templates, Tailwind CSS, frontend components, layout, responsive behavior, themes, forms, empty states, motion, or UI copy in this generated Django SaaS app.
---

# Frontend UI Quality

Use this skill before frontend work that changes what users see or touch.

## First Pass

1. Read `DESIGN.md` and the template/component you are changing.
2. Identify the surface:
   - Product UI: dashboard, settings, auth, admin, docs tools, forms, tables.
   - Brand UI: landing, pricing, blog, marketing pages, public docs intros.
3. Keep the existing Django/Tailwind patterns unless a change clearly improves the workflow.
4. Prefer reusable classes in `frontend/src/styles/index.css` for repeated buttons, panels, cards, code blocks, and focus states.

## Product UI Defaults

Product screens should feel calm, familiar, and task-focused.

- Use restrained color: one primary action color, semantic colors for state, neutral surfaces for structure.
- Use fixed type sizes and a tight hierarchy. Do not use fluid display typography inside app screens.
- Make common workflows fast to scan: clear headings, visible labels, compact controls, stable spacing.
- Every interactive control needs default, hover, focus-visible, active or selected when relevant, disabled, loading or pending when relevant, and error states.
- Prefer skeletons or inline pending states over centered spinners that replace the whole screen.
- Empty states should tell the user the next useful action, not just say the area is empty.

## Brand UI Defaults

Marketing surfaces can be more expressive, but must still avoid generic AI-looking scaffolds.

- Choose a concrete scene and color strategy before adding visual decoration.
- Use real product signals, screenshots, diagrams, or concrete UI examples when possible.
- Keep hero headings within the design system ceiling and verify long generated project names do not overflow.
- Avoid endless same-sized icon card grids. Vary section rhythm and choose layouts that fit the content.

## Hard Bans

Do not introduce these patterns:

- Gradient text.
- Colored side stripes on cards or callouts.
- Nested cards.
- Decorative glassmorphism, blur, bokeh, or gradient blob backgrounds.
- Repeating linear gradient stripe backgrounds.
- Over-rounded cards, panels, inputs, or modals. Cards and panels should usually top out at 16px radius.
- Border plus large soft shadow on the same card, button, input, or panel. Pick structure or elevation, not both.
- Tiny uppercase tracked section eyebrows on every section. Use them only when they carry real information.
- Numbered section markers unless the content is genuinely ordered.
- Hand-drawn or sketchy SVG illustrations as a fallback for missing visual assets.

## Accessibility

- Text contrast must meet WCAG AA: 4.5:1 for body and placeholder text, 3:1 for large text and essential UI graphics.
- Use visible labels for form fields. Placeholders are hints, not labels.
- Preserve keyboard operation and visible `focus-visible` rings.
- Ensure dark mode has equivalent contrast and state visibility.
- Do not gate content on animation. Content should be visible before enhancement.
- Honor `prefers-reduced-motion`; motion should communicate state, not decorate page load.

## Django And Tailwind Rules

- Keep Django forms and server validation as the source of truth.
- Use HTMX for server-rendered updates and Alpine.js for local browser state.
- Keep Jinja valid when adding Tailwind classes around Cookiecutter-rendered values.
- Use `app-focus`, `app-button-*`, `app-input`, `app-card`, and `app-panel` before adding one-off class stacks.
- For repeated patterns, update `frontend/src/styles/index.css` and `DESIGN.md` together.
- For pages that change public setup, navigation, or usage, update README/docs as well.

## Verification

Before finishing:

- Check mobile and desktop layouts for overflow, overlap, clipped menus, and cramped buttons.
- Verify light and dark mode for all changed states.
- Run `npm run lint` when frontend assets or templates changed.
- Run targeted Django tests for changed views/forms and broader checks before shipping risky UI flows.
