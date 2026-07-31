const STORAGE_KEY = "theme";

export function initTheme(root = document) {
  applyTheme(currentTheme());
  root.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    updateButton(button);
    button.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      applyTheme(next);
      document.querySelectorAll("[data-theme-toggle]").forEach(updateButton);
    });
  });
}

function preferredTheme() {
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  return "light";
}

function currentTheme() {
  return localStorage.getItem(STORAGE_KEY) || preferredTheme();
}

function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

function updateButton(button) {
  const theme = currentTheme();
  button.querySelectorAll("[data-theme-icon]").forEach((icon) => {
    icon.classList.toggle("hidden", icon.dataset.themeIcon !== theme);
  });

  const label = button.querySelector("[data-theme-label]");
  if (label) {
    label.textContent = theme === "dark" ? "Dark" : "Light";
  }

  button.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
}
