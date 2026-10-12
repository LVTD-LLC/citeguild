import assert from "node:assert/strict";
import test from "node:test";

const moduleUrl = new URL("../../frontend/src/js/modules/posthog-pageviews.js", import.meta.url);
const privacyUrl = new URL("../../frontend/src/js/modules/posthog-privacy.js", import.meta.url);
const { sanitizePosthogEvent } = await import(privacyUrl);
let moduleId = 0;

async function harness({ consent = true, contentId = "blog:first-guide" } = {}) {
  const events = [];
  const bodyHandlers = {};
  const windowHandlers = {};
  const location = { origin: "https://citeguild.com", pathname: "/blog/first-guide", search: "" };
  const context = (id) => ({
    posthogPageviewEnabled: "true", posthogRoute: "/blog/:slug",
    posthogContentGroup: "blog", ...(id ? { posthogPublicContentId: id } : {}),
  });
  const body = {
    dataset: context(contentId),
    addEventListener: (name, fn) => { bodyHandlers[name] = fn; },
  };
  globalThis.document = { body, referrer: "https://example.com/private?query=secret" };
  globalThis.window = {
    URL, location, SaasAnalytics: { environment: "test", hasConsent: () => consent },
    posthog: { capture: (event, properties) => events.push(sanitizePosthogEvent({ event, properties })) },
    addEventListener: (name, fn) => { windowHandlers[name] = fn; },
    DOMParser: class {
      parseFromString(text) { return { body: { dataset: JSON.parse(text.slice(6)) } }; }
    },
  };
  const { initPosthogPageviews } = await import(`${moduleUrl}?case=${moduleId++}`);
  initPosthogPageviews();
  function navigate(path, dataset) {
    location.pathname = path;
    const xhr = { responseText: `<body>${JSON.stringify(dataset)}` };
    bodyHandlers["htmx:afterSwap"]({ detail: { xhr } });
    return xhr;
  }
  return { events, context, navigate, bodyHandlers, windowHandlers, location, body,
    grant() { consent = true; windowHandlers["saas:analytics-consent-granted"](); } };
}

test("no capture before explicit consent; then one sanitized public guide pageview", async () => {
  const h = await harness({ consent: false });
  assert.equal(h.events.length, 0);
  h.grant();
  assert.equal(h.events.length, 1);
  assert.equal(h.events[0].properties.public_content_id, "blog:first-guide");
  assert.equal(h.events[0].properties.$pathname, "/blog/:slug");
  assert.equal(h.events[0].properties.$referrer, "https://example.com");
  assert.ok(!JSON.stringify(h.events).includes("secret"));
});

test("HTMX guide-to-guide, duplicate swap, public/private navigation and history", async () => {
  const h = await harness();
  const xhr = h.navigate("/blog/second-guide", h.context("blog:second-guide"));
  h.bodyHandlers["htmx:afterSwap"]({ detail: { xhr } });
  assert.deepEqual(h.events.map(e => e.properties.public_content_id), ["blog:first-guide", "blog:second-guide"]);
  h.navigate("/pricing", { posthogPageviewEnabled: "true", posthogRoute: "/pricing", posthogContentGroup: "marketing" });
  assert.equal(h.events.at(-1).properties.public_content_id, undefined);
  h.navigate("/private/sensitive-record", {});
  assert.equal(h.events.length, 3);
  assert.equal(h.body.dataset.posthogPublicContentId, undefined);
  const sanitized = sanitizePosthogEvent({ event: "$pageview", properties: { public_content_id: "blog:stale", $pathname: "/private/sensitive-record" } });
  assert.equal(sanitized.properties.public_content_id, undefined);
  assert.equal(sanitized.properties.$pathname, undefined);
  h.location.pathname = "/blog/second-guide";
  h.windowHandlers.popstate();
  assert.equal(h.events.at(-1).properties.public_content_id, "blog:second-guide");
  h.location.pathname = "/private/sensitive-record";
  h.windowHandlers.popstate();
  assert.equal(h.events.length, 4);
  assert.equal(h.body.dataset.posthogPublicContentId, undefined);
});

test("content IDs cannot escape into person properties or unrelated events", async () => {
  await harness();
  const e = sanitizePosthogEvent({ event: "other", properties: { public_content_id: "private" }, $set: { public_content_id: "private" }, $set_once: { public_content_id: "private" } });
  assert.equal(e.properties.public_content_id, undefined);
  assert.equal(e.$set.public_content_id, undefined);
  assert.equal(e.$set_once.public_content_id, undefined);
});

test("malformed identifiers are omitted and missing consent stays off during navigation", async () => {
  const h = await harness({ contentId: "blog:secret?token=private" });
  assert.equal(h.events[0].properties.public_content_id, undefined);
  const off = await harness({ consent: false });
  off.navigate("/blog/second-guide", off.context("blog:second-guide"));
  assert.equal(off.events.length, 0);
});


test("unseen history navigation clears stale context instead of attributing a guide", async () => {
  const h = await harness();
  h.location.pathname = "/private/not-in-history";
  h.windowHandlers.popstate();
  assert.equal(h.body.dataset.posthogPublicContentId, undefined);
  assert.equal(window.SaasAnalytics.pageviewContext.enabled, false);
  assert.equal(h.events.length, 1);
});

test("a delayed pageview cannot acquire a different guide identity", async () => {
  await harness();
  const e = sanitizePosthogEvent({ event: "$pageview", properties: { public_content_id: "blog:previous-guide" } });
  assert.equal(e.properties.public_content_id, undefined);
});
