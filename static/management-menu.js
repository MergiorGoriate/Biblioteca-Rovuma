const button = document.getElementById("management-menu-toggle");
const navigation = document.getElementById("management-navigation");
const narrowScreen = window.matchMedia("(max-width: 760px)");

function setMenu(expanded) {
  navigation.hidden = !expanded;
  button.setAttribute("aria-expanded", String(expanded));
}

function updateLayout() {
  const focusInMenu = navigation.contains(document.activeElement);
  if (narrowScreen.matches) {
    button.hidden = false;
    if (focusInMenu) button.focus();
    setMenu(false);
  } else {
    setMenu(true);
    if (document.activeElement === button) navigation.querySelector("a").focus();
    button.hidden = true;
  }
}

button.addEventListener("click", () => setMenu(navigation.hidden));
navigation.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && narrowScreen.matches) {
    setMenu(false);
    button.focus();
  }
});
narrowScreen.addEventListener("change", updateLayout);
updateLayout();
