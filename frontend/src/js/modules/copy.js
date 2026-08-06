import { copyText } from "./clipboard.js";

export function initCopyButtons(root = document) {
  root.querySelectorAll("[data-copy-button]").forEach((button) => {
    if (button.dataset.copyBound === "true") {
      return;
    }

    button.dataset.copyBound = "true";
    button.addEventListener("click", async () => {
      const sourceSelector = button.dataset.copySource;
      const source = sourceSelector ? document.querySelector(sourceSelector) : null;
      const label = button.querySelector("[data-copy-label]") || button;
      const original = label.textContent;
      let text = source?.value || source?.textContent || "";
      let copied = false;

      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      label.textContent = "Copying…";
      try {
        if (button.dataset.copyUrl) {
          const headers = { Accept: "application/json" };
          if (button.dataset.copyCsrfToken) {
            headers["X-CSRFToken"] = button.dataset.copyCsrfToken;
          }
          const response = await fetch(button.dataset.copyUrl, {
            cache: "no-store",
            credentials: "same-origin",
            headers,
            method: button.dataset.copyMethod || "GET",
          });
          if (!response.ok) {
            throw new Error("Copy source request failed");
          }
          const payload = await response.json();
          text = payload[button.dataset.copyResponseKey || "prompt"] || "";
        }
        copied = Boolean(text) && (await copyText(text));
      } catch {
        copied = false;
      } finally {
        button.disabled = false;
        button.removeAttribute("aria-busy");
      }

      label.textContent = copied ? "Copied" : "Copy failed";
      window.clearTimeout(Number(button.dataset.resetTimer));
      button.dataset.resetTimer = window.setTimeout(() => {
        label.textContent = original;
      }, 1600);
    });
  });
}
