const SHORTCUT_SELECTOR = "[data-shortcut-key]";

export function initKeyboardShortcuts(root = document) {
  const ownerDocument = root.ownerDocument || root;
  const shortcuts = new Map();

  function registerShortcuts() {
    shortcuts.clear();
    ownerDocument.querySelectorAll(SHORTCUT_SELECTOR).forEach((element) => {
      const key = normalizedShortcutKey(element.dataset.shortcutKey);
      if (key && !shortcuts.has(key)) {
        shortcuts.set(key, element);
      }
    });
  }

  registerShortcuts();

  ownerDocument.addEventListener("htmx:afterSwap", registerShortcuts);
  ownerDocument.addEventListener("keydown", (event) => {
    if (shouldIgnoreKeydown(event)) {
      return;
    }

    const target = shortcuts.get(event.key.toLowerCase());
    if (!target || target.matches("[aria-disabled='true'], :disabled")) {
      return;
    }

    event.preventDefault();
    target.click();
  });
}

function normalizedShortcutKey(key) {
  const normalized = key?.trim().toLowerCase();
  return normalized && normalized.length === 1 ? normalized : "";
}

function shouldIgnoreKeydown(event) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey || event.isComposing) {
    return true;
  }

  const key = event.key.toLowerCase();
  if (key.length !== 1) {
    return true;
  }

  return isTextEntryTarget(event.target);
}

function isTextEntryTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }

  const textEntry = target.closest("input, textarea, select, [contenteditable], [role='textbox']");
  if (!textEntry) {
    return false;
  }

  if (!textEntry.hasAttribute("contenteditable")) {
    return true;
  }

  return textEntry.getAttribute("contenteditable")?.toLowerCase() !== "false";
}
