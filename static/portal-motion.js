(() => {
  if (typeof Element.prototype.animate !== "function") return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const activeAnimations = new Set();

  function animateEntrance(element, firstFrame, duration, delay = 0) {
    if (!element || reducedMotion.matches) return;

    const animation = element.animate([firstFrame, { opacity: 1, transform: "none" }], {
      duration,
      delay,
      easing: "cubic-bezier(0.2, 0.65, 0.3, 1)",
      fill: "backwards",
    });
    activeAnimations.add(animation);
    animation.addEventListener("finish", () => activeAnimations.delete(animation), { once: true });
    animation.addEventListener("cancel", () => activeAnimations.delete(animation), { once: true });
  }

  reducedMotion.addEventListener?.("change", ({ matches }) => {
    if (matches) activeAnimations.forEach((animation) => animation.cancel());
  });

  animateEntrance(document.querySelector(".portal-hero-content"), {
    opacity: 0.8, transform: "translateY(10px)",
  }, 360);
  animateEntrance(document.querySelector(".portal-hero-image"), { opacity: 0.82 }, 420);

  if (!("IntersectionObserver" in window)) return;

  const observer = new IntersectionObserver((entries) => {
    let visibleIndex = 0;
    for (const { target, isIntersecting } of entries) {
      if (!isIntersecting) continue;

      observer.unobserve(target);
      animateEntrance(target, {
        opacity: 0.65, transform: "translateY(12px)",
      }, 320, Math.min(visibleIndex, 3) * 40);
      visibleIndex += 1;
    }
  }, { threshold: 0.18 });

  document.querySelectorAll(".portal-book, .portal-section .grid > article").forEach((card) => {
    observer.observe(card);
  });
})();
