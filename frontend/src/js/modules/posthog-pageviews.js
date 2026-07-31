import { posthogAttribution } from "./posthog-attribution.js";

const capturedHtmxRequests = new WeakSet();
const pageviewContextsByUrl = new Map();
let includeDocumentReferrer = true;
let lastCaptureKey = "";

function contextSnapshot() {
  const dataset = document.body?.dataset || {};
  return {
    contentGroup: dataset.posthogContentGroup || "",
    enabled: dataset.posthogPageviewEnabled === "true",
    route: dataset.posthogRoute || "",
  };
}

function syncPrivacyContext() {
  window.SaasAnalytics.pageviewContext = contextSnapshot();
}

function pageviewContext() {
  const context = contextSnapshot();
  if (!context.enabled || !context.route.startsWith("/") || !context.contentGroup) return null;
  return context;
}

function campaignProperties(search) {
  const properties = {};
  const searchParams = new URLSearchParams(search);
  posthogAttribution.campaignKeys.forEach((key) => {
    const value = posthogAttribution.safeCampaignValue(searchParams.get(key));
    if (value) properties[key] = value;
  });
  return properties;
}

function referrerProperties() {
  const referrerValue = includeDocumentReferrer ? document.referrer : "";
  includeDocumentReferrer = false;
  if (!referrerValue) return {};

  try {
    const referrer = new window.URL(referrerValue);
    if (
      !["http:", "https:"].includes(referrer.protocol) ||
      referrer.origin === window.location.origin
    ) {
      return {};
    }
    return {
      $referrer: referrer.origin,
      $referring_domain: referrer.hostname,
    };
  } catch (_error) {
    return {};
  }
}

function capturePosthogPageview(force = false) {
  const analytics = window.SaasAnalytics;
  const context = pageviewContext();
  if (!context || !analytics.hasConsent?.() || typeof window.posthog?.capture !== "function") {
    return false;
  }

  const campaign = campaignProperties(window.location.search);
  const captureKey = JSON.stringify([context.route, context.contentGroup, campaign]);
  if (force !== true && captureKey === lastCaptureKey) return false;

  const currentUrl = `${window.location.origin}${context.route}`;
  const referrer = referrerProperties();
  analytics.persistAttribution?.({
    ...campaign,
    landing_route: context.route,
    ...(referrer.$referrer ? { referrer: referrer.$referrer } : {}),
    ...(referrer.$referring_domain
      ? { referring_domain: referrer.$referring_domain }
      : {}),
  });
  window.posthog.capture("$pageview", {
    $current_url: currentUrl,
    $pathname: context.route,
    ...referrer,
    content_group: context.contentGroup,
    environment: analytics.environment || "unknown",
    event_version: 1,
    route: context.route,
    ...campaign,
  });
  lastCaptureKey = captureKey;
  return true;
}

function rememberContext() {
  pageviewContextsByUrl.set(
    `${window.location.origin}${window.location.pathname}`,
    contextSnapshot(),
  );
}

function restoreContext() {
  const context = pageviewContextsByUrl.get(
    `${window.location.origin}${window.location.pathname}`,
  );
  const dataset = document.body?.dataset;
  if (!context || !dataset) return false;
  dataset.posthogPageviewEnabled = context.enabled ? "true" : "false";
  if (context.route) dataset.posthogRoute = context.route;
  else delete dataset.posthogRoute;
  if (context.contentGroup) dataset.posthogContentGroup = context.contentGroup;
  else delete dataset.posthogContentGroup;
  syncPrivacyContext();
  return true;
}

function updateContextFromHtmxResponse(event) {
  const responseText = event?.detail?.xhr?.responseText;
  if (
    typeof responseText !== "string" ||
    !responseText.toLowerCase().includes("<body") ||
    typeof window.DOMParser !== "function"
  ) {
    return null;
  }
  const responseDocument = new window.DOMParser().parseFromString(responseText, "text/html");
  const responseContext = responseDocument.body?.dataset || {};
  const dataset = document.body?.dataset;
  if (!dataset) return null;

  if (responseContext.posthogPageviewEnabled === "true") {
    dataset.posthogPageviewEnabled = "true";
    dataset.posthogRoute = responseContext.posthogRoute || "";
    dataset.posthogContentGroup = responseContext.posthogContentGroup || "";
    syncPrivacyContext();
    return "eligible";
  }
  dataset.posthogPageviewEnabled = "false";
  delete dataset.posthogRoute;
  delete dataset.posthogContentGroup;
  syncPrivacyContext();
  return "disabled";
}

function captureHtmxPageview(event) {
  const contextUpdate = updateContextFromHtmxResponse(event);
  const request = event?.detail?.xhr;
  if (contextUpdate === "eligible" && request && capturedHtmxRequests.has(request)) return;
  if (contextUpdate === "eligible" && request) capturedHtmxRequests.add(request);
  rememberContext();
  capturePosthogPageview(contextUpdate === "eligible");
}

export function initPosthogPageviews() {
  syncPrivacyContext();
  rememberContext();
  capturePosthogPageview();
  document.body?.addEventListener("htmx:afterSwap", captureHtmxPageview);
  window.addEventListener("popstate", () => {
    if (restoreContext()) capturePosthogPageview(true);
  });
  window.addEventListener("saas:analytics-consent-granted", () =>
    capturePosthogPageview(true),
  );
}
