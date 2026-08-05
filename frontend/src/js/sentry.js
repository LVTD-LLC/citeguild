import * as Sentry from "@sentry/browser";

function stripUrlDetails(value) {
  try {
    const url = new URL(value, window.location.origin);
    return `${url.origin}${url.pathname}`;
  } catch {
    return undefined;
  }
}

function sanitizeBreadcrumb(breadcrumb) {
  if (!breadcrumb.data) {
    return breadcrumb;
  }

  for (const field of ["url", "from", "to"]) {
    if (breadcrumb.data[field]) {
      breadcrumb.data[field] = stripUrlDetails(breadcrumb.data[field]);
    }
  }
  return breadcrumb;
}

const configElement = document.getElementById("sentry-browser-config");

if (configElement) {
  const config = JSON.parse(configElement.textContent);
  const tracesSampleRate = Number(config.traces_sample_rate);

  if (config.enabled && config.dsn) {
    Sentry.init({
      dsn: config.dsn,
      enableLogs: true,
      environment: config.environment,
      integrations: [Sentry.browserTracingIntegration()],
      maxBreadcrumbs: 100,
      release: config.release || undefined,
      sendDefaultPii: false,
      tracePropagationTargets: [window.location.origin],
      tracesSampleRate:
        Number.isFinite(tracesSampleRate) && tracesSampleRate >= 0 && tracesSampleRate <= 1
          ? tracesSampleRate
          : 0,
      beforeBreadcrumb: sanitizeBreadcrumb,
      beforeSend(event) {
        if (event.request?.url) {
          event.request.url = stripUrlDetails(event.request.url);
        }
        return event;
      },
    });
  }
}
