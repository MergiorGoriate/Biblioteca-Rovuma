const themeStorageKey = "rovuma-admin-theme";
const themeRoot = document.documentElement;

function applyManagementTheme(theme) {
  themeRoot.dataset.managementTheme = theme;
}

try {
  applyManagementTheme(localStorage.getItem(themeStorageKey) === "light" ? "light" : "dark");
} catch {
  applyManagementTheme("dark");
}

window.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("management-theme-toggle");
  const label = toggle.querySelector(".theme-label");

  function updateThemeButton() {
    const nextTheme = themeRoot.dataset.managementTheme === "light" ? "Escuro" : "Claro";
    const description = `Activar modo ${nextTheme.toLowerCase()}`;
    label.textContent = nextTheme;
    toggle.setAttribute("aria-label", description);
    toggle.title = description;
  }

  toggle.addEventListener("click", () => {
    const theme = themeRoot.dataset.managementTheme === "light" ? "dark" : "light";
    applyManagementTheme(theme);
    updateThemeButton();
    try {
      localStorage.setItem(themeStorageKey, theme);
    } catch {
      // Changing the current page still works when storage is disabled.
    }
  });
  updateThemeButton();
  toggle.hidden = false;
});
