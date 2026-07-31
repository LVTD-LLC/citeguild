const campaignKeys = Object.freeze([
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
  "campaign_id",
]);
const campaignValuePattern = /^[a-z0-9][a-z0-9 ._\-/]*$/i;

function safeCampaignValue(value) {
  const normalized = typeof value === "string" ? value.trim() : "";
  return normalized && normalized.length <= 100 && campaignValuePattern.test(normalized)
    ? normalized
    : "";
}

export const posthogAttribution = Object.freeze({
  campaignKeys,
  safeCampaignValue,
  version: 1,
});
