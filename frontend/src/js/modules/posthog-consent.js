import { posthogAttribution } from "./posthog-attribution.js";

const consentCookie = "analytics_consent";
const attributionCookie = "marketing_attribution";
const maxAttributionCookieValueLength = 3800;
const attributionSignalKeys = [
  ...posthogAttribution.campaignKeys,
  "referrer",
  "referring_domain",
];
const touchKeys = [
  ...posthogAttribution.campaignKeys,
  "landing_route",
  "referrer",
  "referring_domain",
];
const domainPattern = /^[a-z0-9.-]+$/i;

function cookieValue(name) {
  const prefix = `${name}=`;
  return (
    (document.cookie || "")
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(prefix))
      ?.slice(prefix.length) || ""
  );
}

function setCookie(name, value, maxAge) {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${name}=${value}; Path=/; Max-Age=${maxAge}; SameSite=Lax${secure}`;
}

function safeReferrer(value) {
  try {
    const referrer = new window.URL(String(value || ""));
    return ["http:", "https:"].includes(referrer.protocol) ? referrer.origin : "";
  } catch (_error) {
    return "";
  }
}

function sanitizeTouch(touch) {
  if (!touch || typeof touch !== "object") return {};
  const sanitized = {};
  posthogAttribution.campaignKeys.forEach((key) => {
    const value = posthogAttribution.safeCampaignValue(touch[key]);
    if (value) sanitized[key] = value;
  });
  const route = typeof touch.landing_route === "string" ? touch.landing_route : "";
  if (route.startsWith("/") && !route.includes("?") && route.length <= 160) {
    sanitized.landing_route = route;
  }
  const referrer = safeReferrer(touch.referrer);
  if (referrer) sanitized.referrer = referrer;
  const domain =
    typeof touch.referring_domain === "string"
      ? touch.referring_domain.trim().toLowerCase()
      : "";
  if (domain && domain.length <= 253 && domainPattern.test(domain)) {
    sanitized.referring_domain = domain;
  }
  return sanitized;
}

function canonicalAttribution(firstTouch, latestTouch) {
  const attribution = {
    version: posthogAttribution.version,
    first_touch: sanitizeTouch(firstTouch),
    latest_touch: sanitizeTouch(latestTouch),
  };
  const expendableKeys = [
    "referrer",
    "referring_domain",
    "utm_term",
    "utm_content",
    "campaign_id",
    "utm_medium",
    "utm_campaign",
  ];
  for (const key of expendableKeys) {
    if (encodeURIComponent(JSON.stringify(attribution)).length <= maxAttributionCookieValueLength) {
      break;
    }
    delete attribution.latest_touch[key];
    delete attribution.first_touch[key];
  }
  return attribution;
}

function readMarketingAttribution() {
  try {
    const stored = JSON.parse(decodeURIComponent(cookieValue(attributionCookie))) || {};
    if (stored.version !== posthogAttribution.version) return {};
    return canonicalAttribution(stored.first_touch, stored.latest_touch);
  } catch (_error) {
    return {};
  }
}

function personAttribution(attribution = readMarketingAttribution()) {
  const firstTouch = attribution.first_touch || {};
  const currentTouch = attribution.latest_touch || {};
  if (Object.keys(firstTouch).length === 0 && Object.keys(currentTouch).length === 0) {
    return { current: {}, first: {} };
  }
  const current = Object.fromEntries(touchKeys.map((key) => [`current_touch_${key}`, null]));
  Object.entries(currentTouch).forEach(([key, value]) => {
    current[`current_touch_${key}`] = value;
  });
  const first = Object.fromEntries(
    Object.entries(firstTouch).map(([key, value]) => [`first_touch_${key}`, value]),
  );
  return { current, first };
}

function showBanner(show) {
  const banner = document.querySelector("[data-analytics-consent]");
  if (banner) banner.hidden = !show;
}

function syncIdentityAndAttribution(attribution = readMarketingAttribution()) {
  const analytics = window.SaasAnalytics;
  if (!analytics.hasConsent()) return;
  const identity = analytics.identity || {};
  if (identity.distinctId && window.posthog?.get_distinct_id?.() !== identity.distinctId) {
    window.posthog?.identify?.(identity.distinctId);
  }
  const properties = personAttribution(attribution);
  if (
    (Object.keys(properties.current).length > 0 || Object.keys(properties.first).length > 0) &&
    typeof window.posthog?.setPersonProperties === "function"
  ) {
    window.posthog.setPersonProperties(properties.current, properties.first);
  }
}

function persistMarketingAttribution(touch) {
  const analytics = window.SaasAnalytics;
  if (!analytics.hasConsent()) return;
  const sanitized = sanitizeTouch(touch);
  if (Object.keys(sanitized).length === 0) return;
  const existing = readMarketingAttribution();
  const hasFirstTouch = Object.keys(existing.first_touch || {}).length > 0;
  const hasAttributionSignal = attributionSignalKeys.some((key) => key in sanitized);
  if (hasFirstTouch && !hasAttributionSignal) return;
  if (hasFirstTouch && JSON.stringify(existing.latest_touch) === JSON.stringify(sanitized)) return;
  const attribution = canonicalAttribution(
    hasFirstTouch ? existing.first_touch : sanitized,
    sanitized,
  );
  setCookie(
    attributionCookie,
    encodeURIComponent(JSON.stringify(attribution)),
    60 * 60 * 24 * 180,
  );
  syncIdentityAndAttribution(attribution);
}

function choose(value) {
  const analytics = window.SaasAnalytics;
  analytics.consent = value;
  setCookie(consentCookie, value, 60 * 60 * 24 * 365);
  showBanner(false);
  if (value === "granted") {
    window.posthog?.opt_in_capturing?.();
    syncIdentityAndAttribution();
    window.dispatchEvent?.(new window.Event("saas:analytics-consent-granted"));
  } else {
    window.posthog?.opt_out_capturing?.();
    setCookie(attributionCookie, "", 0);
  }
}

export function initPosthogConsent() {
  const analytics = window.SaasAnalytics;
  analytics.consent = cookieValue(consentCookie);
  analytics.hasConsent = () => analytics.consent === "granted";
  analytics.persistAttribution = persistMarketingAttribution;

  document
    .querySelector("[data-analytics-consent-accept]")
    ?.addEventListener("click", () => choose("granted"));
  document
    .querySelector("[data-analytics-consent-decline]")
    ?.addEventListener("click", () => choose("denied"));

  if (analytics.hasConsent()) {
    window.posthog?.opt_in_capturing?.();
    syncIdentityAndAttribution();
    showBanner(false);
  } else {
    window.posthog?.opt_out_capturing?.();
    showBanner(analytics.consent !== "denied");
  }
}
