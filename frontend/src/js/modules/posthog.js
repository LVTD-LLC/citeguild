import { initPosthogConsent } from "./posthog-consent.js";
import { initPosthogCtas } from "./posthog-ctas.js";
import { initPosthogPageviews } from "./posthog-pageviews.js";

export function initPosthog() {
  initPosthogConsent();
  initPosthogCtas();
  initPosthogPageviews();

  document.addEventListener("submit", (event) => {
    if (event.target.matches("form[data-posthog-reset]")) {
      window.posthog?.reset?.();
    }
  });
}
