function captureCta(element) {
  const analytics = window.SaasAnalytics;
  if (!element || !analytics?.hasConsent?.()) return;

  let destination = "";
  try {
    destination = new window.URL(element.href || element.action, window.location.origin).pathname;
  } catch (_error) {
    // Invalid destinations use the empty allowlisted value.
  }

  window.posthog?.capture?.(`${analytics.eventPrefix}_marketing_cta_clicked`, {
    event_version: 1,
    environment: analytics.environment || "unknown",
    cta_name: element.dataset.posthogCta,
    cta_location: element.dataset.posthogCtaLocation || "unknown",
    destination,
  });
}

export function initPosthogCtas() {
  document.addEventListener("click", (event) => {
    captureCta(event.target.closest?.("a[data-posthog-cta]"));
  });
  document.addEventListener("submit", (event) => {
    captureCta(event.target.closest?.("form[data-posthog-cta]"));
  });
}
