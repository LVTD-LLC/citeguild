export async function copyText(text) {
  const textPromise = Promise.resolve(text);

  // WebKit can discard user activation while remote copy content is loading.
  // Start the clipboard write during the click and let the ClipboardItem resolve later.
  if (typeof text?.then === "function" && navigator.clipboard?.write && window.ClipboardItem) {
    try {
      const blobPromise = textPromise.then((resolvedText) => {
        if (!resolvedText) {
          throw new Error("Copy text is empty");
        }
        return new Blob([resolvedText], { type: "text/plain" });
      });
      await navigator.clipboard.write([new window.ClipboardItem({ "text/plain": blobPromise })]);
      return true;
    } catch {
      // Fall back for browsers without promise-backed ClipboardItem support.
    }
  }

  const resolvedText = await textPromise;
  if (!resolvedText) {
    return false;
  }

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(resolvedText);
      return true;
    } catch {
      // Fall back for restricted clipboard contexts.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = resolvedText;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();

  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}
