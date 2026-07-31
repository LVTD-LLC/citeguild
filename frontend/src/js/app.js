import { initCopyButtons } from "./modules/copy.js";
import { initDocsEnhancements } from "./modules/docs.js";
import { initMessages } from "./modules/messages.js";
import { initKeyboardShortcuts } from "./modules/shortcuts.js";
import { initPosthog } from "./modules/posthog.js";
import { initTheme } from "./modules/theme.js";
import { initUserSettingsCache } from "./modules/user-settings.js";

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initMessages();
  initCopyButtons();
  initDocsEnhancements();
  initKeyboardShortcuts();

  initPosthog();

  initUserSettingsCache();
});
