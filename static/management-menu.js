const button = document.getElementById("management-menu-toggle");
const rail = document.getElementById("management-navigation");
const narrowScreen = window.matchMedia("(max-width: 740px)");

function setMenu(expanded) {
  rail.hidden = !expanded;
  button.setAttribute("aria-expanded", String(expanded));
}

function updateLayout() {
  const focusInMenu = rail.contains(document.activeElement);
  if (narrowScreen.matches) {
    button.hidden = false;
    if (focusInMenu) button.focus();
    setMenu(false);
  } else {
    setMenu(true);
    if (document.activeElement === button) rail.querySelector("nav a").focus();
    button.hidden = true;
  }
}

button.addEventListener("click", () => setMenu(rail.hidden));
rail.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && narrowScreen.matches) {
    setMenu(false);
    button.focus();
  }
});
narrowScreen.addEventListener("change", updateLayout);
updateLayout();
