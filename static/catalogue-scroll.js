const backToTop = document.getElementById("catalogue-back-to-top");
const catalogueTitle = document.getElementById("catalogue-title");
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function updateBackToTop() {
  backToTop.hidden = window.scrollY <= 64;
}

window.addEventListener("scroll", updateBackToTop, { passive: true });
window.addEventListener("pageshow", updateBackToTop);

backToTop.addEventListener("click", () => {
  catalogueTitle.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: prefersReducedMotion.matches ? "auto" : "smooth" });
});

updateBackToTop();
