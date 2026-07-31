export function initUserSettingsCache() {
  const body = document.body;
  if (!body?.hasAttribute("data-user-settings-cache")) {
    return;
  }

  fetch("/api/user/settings")
    .then((response) => {
      if (!response.ok) {
        throw new Error("Failed to fetch user settings.");
      }
      return response.json();
    })
    .then((data) => {
      localStorage.setItem("userSettings", JSON.stringify(data));
    })
    .catch((error) => {
      console.error("Error fetching user settings:", error);
    });
}
