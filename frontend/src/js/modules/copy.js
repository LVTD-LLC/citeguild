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
      const text = source?.value || source?.textContent || "";
      const copied = await copyText(text);

      label.textContent = copied ? "Copied" : "Copy failed";
      window.clearTimeout(Number(button.dataset.resetTimer));
      button.dataset.resetTimer = window.setTimeout(() => {
        label.textContent = original;
      }, 1600);
    });
  });
}
