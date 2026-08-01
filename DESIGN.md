---
version: alpha
name: "CiteGuild"
description: "Calm, trustworthy product system for CiteGuild's source-discovery and indexing workflows."
colors:
  primary: "#15803D"
  primary-hover: "#166534"
  primary-soft: "#DCFCE7"
  secondary: "#0F172A"
  secondary-soft: "#E2E8F0"
  accent: "#2563EB"
  neutral: "#F8FAFC"
  surface: "#FFFFFF"
  surface-muted: "#F1F5F9"
  surface-dark: "#020617"
  border: "#E2E8F0"
  border-dark: "#1E293B"
  text: "#0F172A"
  text-muted: "#475569"
  text-inverse: "#FFFFFF"
  success: "#166534"
  warning: "#F59E0B"
  danger: "#DC2626"
typography:
  headline-display:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 60px
    fontWeight: 800
    lineHeight: 1
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 48px
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: -0.035em
  headline-md:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 30px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: -0.025em
  headline-sm:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.65
  body-md:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.65
  body-sm:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  label-md:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.3
  label-caps:
    fontFamily: Inter, ui-sans-serif, system-ui, sans-serif
    fontSize: 12px
    fontWeight: 700
    lineHeight: 1
    letterSpacing: 0.08em
  code-sm:
    fontFamily: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.6
rounded:
  none: 0px
  sm: 6px
  md: 10px
  lg: 14px
  xl: 16px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  control: 12px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
  section-y: 96px
  page-x: 24px
  container: 1200px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.text-inverse}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.control}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.text-inverse}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.control}"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.text-inverse}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    padding: "{spacing.control}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.xl}"
    padding: "{spacing.lg}"
  card-muted:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text}"
    rounded: "{rounded.xl}"
    padding: "{spacing.lg}"
  app-shell:
    backgroundColor: "{colors.neutral}"
    textColor: "{colors.text}"
  nav:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.full}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "{spacing.control}"
  badge-success:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.success}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  badge-warning:
    backgroundColor: "{colors.warning}"
    textColor: "{colors.surface-dark}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  badge-neutral:
    backgroundColor: "{colors.secondary-soft}"
    textColor: "{colors.secondary}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.full}"
    padding: "{spacing.sm}"
  link:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.accent}"
    typography: "{typography.body-md}"
  divider-light:
    backgroundColor: "{colors.border}"
    height: 1px
  divider-dark:
    backgroundColor: "{colors.border-dark}"
    height: 1px
  muted-copy:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-muted}"
    typography: "{typography.body-sm}"
---

# CiteGuild Design System

## Overview

This file is the project-level design source of truth for humans and AI coding agents. It follows the public Google Labs Code [`DESIGN.md`](https://github.com/google-labs-code/design.md) alpha format: YAML design tokens first, then markdown guidance explaining how to apply them.

CiteGuild should feel like dependable research infrastructure, not an SEO marketplace or a growth-hack dashboard. The authenticated product is quiet, precise, and status-oriented; marketing surfaces can explain the network effect more expressively, but must keep the promise grounded in relevant source discovery.

The primary user may be a person configuring sites or an agent consuming search. Human screens should make the system state legible: subscription eligibility, sitemap health, indexing progress, active/inactive article counts, agent connection, and detected citations. Never imply that a citation is promised or that CiteGuild caused a detected link.

## Colors

The palette uses practical neutrals with a confident green for healthy discovery and indexing actions.

- **Primary (#15803D):** Main action color for subscription, Add Site, Copy Prompt, selected states, and healthy discovery/indexing signals.
- **Secondary (#0F172A):** Deep slate for headlines, app chrome, and high-contrast UI surfaces.
- **Accent (#2563EB):** Secondary action/link color. Use it for navigation emphasis and informational affordances, not the main conversion path.
- **Neutral/Surface (#F8FAFC / #FFFFFF / #F1F5F9):** Light surfaces for pages, cards, forms, dashboards, and marketing sections.
- **Semantic colors:** Green for success, amber for warning, red for destructive or error states.

Do not use green to suggest guaranteed SEO growth or a promised backlink. Detected citations, retrieval scores, and indexing state need explicit labels and supporting text rather than color-only meaning.

Check contrast whenever colors move. Body copy, helper text, labels, placeholders, and disabled-but-readable text must meet WCAG AA contrast on both light and dark surfaces. Gray text on tinted backgrounds often fails; use a darker shade of the surface hue or move closer to `text`.

## Typography

Use a system sans-serif stack for speed, reliability, and low setup friction. Add a brand font later only if it improves the product enough to justify the dependency.

- **Headlines:** Bold with restrained tight tracking for landing pages, docs intros, and major empty states. Keep display tracking at `-0.04em` or looser.
- **Body:** 16px default with generous line height for readable forms, settings pages, docs, and dashboards.
- **Labels:** Medium-weight labels for form controls and action buttons.
- **Caps labels:** Use sparingly for badges and metadata. Do not put a tiny uppercase eyebrow above every section.
- **Code:** Monospace for API examples, environment variables, commands, tokens, and identifiers.

Product UI should use fixed type sizes rather than viewport-fluid typography. Reserve hero-scale type for true public heroes; inside app panels, settings pages, dashboards, modals, and cards, keep headings compact enough that controls and content remain scannable. Use `text-wrap: balance` on headings and `text-wrap: pretty` on prose where supported.

## Layout

Use simple responsive layouts that work well for server-rendered Django pages.

- Keep page content inside a centered max-width container (`1200px`) with `24px` mobile-safe horizontal padding.
- Use generous vertical rhythm on marketing pages and tighter spacing in authenticated app screens.
- Prefer boring, predictable structure: single column on mobile, 2-column feature areas, and 3-column card groups only when content is truly symmetrical.
- Forms should be narrow enough to scan comfortably. Dashboards can use wider containers, but avoid dense data walls without hierarchy.
- Design empty, loading, error, and success states as first-class UI, not afterthoughts.
- Give fixed-format UI, such as toolbars, icon buttons, counters, tables, and cards, stable dimensions so hover states, labels, and dynamic content do not shift the layout.
- Make the dashboard sequence obvious: subscribe, add a sitemap-backed site,
  wait for indexing, connect an agent, then inspect detected network activity.
- Prefer a scannable site list and status detail over a dense generic KPI wall.
  Put recent actionable sync failures near the affected site.

## Elevation & Depth

Depth should come from borders, spacing, and subtle shadows.

- Default cards use light backgrounds, clear borders, and rounded corners.
- Use shadows only for overlays, menus, modals, and important hover states.
- Dark surfaces are reserved for headers, footers, code examples, and high-contrast hero sections.
- Avoid heavy glassmorphism, noisy gradients, and decorative effects that make forms or tables harder to read.
- Avoid the ghost-card pattern: a 1px border plus a large soft drop shadow on the same card, button, input, or panel. Pick a clear border or a purposeful elevation.

## Shapes

The default shape language is friendly but restrained.

- Use pill buttons for primary actions and navigation CTAs.
- Use `10px`–`16px` radius for inputs, cards, panels, and modal containers.
- Use full-radius badges for status labels.
- Keep radius choices consistent within each screen; inconsistency makes generated products feel stitched together.

## Components

- **Primary button:** Primary background, white text, pill radius, medium-bold label. Use for the single most important action in a section.
- **Secondary button:** White or muted background, slate text, border when needed. Use for navigation, cancel, and lower-priority actions.
- **Danger button:** Red background, white text. Use only for irreversible destructive actions and pair with confirmation UI.
- **Cards:** White/muted surfaces with rounded corners and borders. Keep one clear purpose per card.
- **Forms:** Visible labels, clear helper/error text, high-contrast focus rings, and full-width controls on mobile.
- **Navigation:** Simple top nav with clear product name, primary links, auth/account actions, and accessible mobile behavior.
- **Tables/lists:** Prioritize scanability: sticky or repeated context where needed, muted metadata, and explicit empty states.
- **Docs/code blocks:** Monospace code, copyable commands when possible, and examples that match the generated project structure.
- **Site status:** Show sitemap URL/domain, last successful sync, indexed,
  inactive, pending, and failed counts with text labels and timestamps. Never
  communicate state by color alone.
- **Copy Prompt:** Treat this as the primary post-indexing onboarding action.
  Provide clear copy success/failure feedback and link to MCP, CLI, and API
  setup choices.
- **Search results:** Lead with title and canonical domain, then a bounded
  excerpt/summary, relevance indication, and last-seen time. The interface
  helps the agent assess fit; it must not present an automatic "insert link"
  action.
- **Detected citations:** Use “detected citation” or “detected link,” show source
  and target pages plus first/last seen and active state, and avoid causal or
  guaranteed-placement language.

Every interactive component needs default, hover, focus-visible, active or selected when relevant, disabled, loading or pending when relevant, and error states. If a control can submit, delete, copy, save, authenticate, or navigate, design the state after success and failure before shipping it.

## Motion

Motion should communicate state, not decorate page load.

- Keep ordinary transitions around 150ms-250ms.
- Animate opacity and transform before layout properties.
- Do not hide content until JavaScript-triggered reveal animations run.
- Provide reduced-motion behavior with `prefers-reduced-motion`.
- Use skeletons or inline pending states for loading; avoid replacing useful context with a centered spinner.

## Frontend Quality Bar

Before shipping generated-project UI changes:

- Read `.agents/skills/frontend-ui-quality/SKILL.md` for the portable UI quality workflow.
- Check light and dark mode.
- Check mobile and desktop layouts for overflow, clipped menus, text collisions, and cramped buttons.
- Verify form errors, empty states, success messages, destructive confirmations, and disabled states.
- Keep repeated patterns in `frontend/src/styles/index.css` and update this file when changing tokens or component rules.

## Do's and Don'ts

- Do update this file when the brand, product vocabulary, UI conventions, or component rules change.
- Do keep YAML tokens and markdown descriptions consistent.
- Do preserve WCAG AA contrast for text, buttons, alerts, and form states.
- Do design for both anonymous marketing pages and authenticated SaaS app screens.
- Do keep guidance agent-neutral: useful to humans and any coding agent.
- Do use “site” in customer-facing UI; use “project” only where an API or
  internal model deliberately exposes that term.
- Do say “detected citation” for an observed member-to-member relationship and
  “relevance” for search ordering.
- Don't use backlink-marketplace conventions such as credits, exchange
  balances, guaranteed placements, DR promises, outreach inboxes, or
  reciprocity status.
- Don't describe inactive articles as deleted; their history is retained.
- Don't introduce a new font, color, radius, or shadow style for a single screen without updating the design system.
- Don't make AI-agent instructions vendor-specific; use plain project conventions and file paths.
- Don't let generated pages depend on remote design assets unless the project explicitly adds them.
- Don't use gradient text, colored side stripes, nested cards, repeated decorative card grids, over-rounded panels, or tiny uppercase section labels as default scaffolding.
