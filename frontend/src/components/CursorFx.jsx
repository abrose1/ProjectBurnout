import { useEffect } from "react";

/**
 * Click ember burst on .layout (terracotta + coal particles).
 * Flame cursor is CSS on .layout (see global.css). Disabled for coarse pointers
 * and prefers-reduced-motion. Skips input, textarea, and select.
 */
export function CursorFx() {
  useEffect(() => {
    const mqMove = window.matchMedia("(prefers-reduced-motion: reduce)");
    const mqFine = window.matchMedia("(hover: hover) and (pointer: fine)");
    if (mqMove.matches || !mqFine.matches) {
      return undefined;
    }

    const layout = document.querySelector(".layout");
    if (!layout) {
      return undefined;
    }

    const onPointerDown = (e) => {
      if (e.button !== 0) return;
      if (e.target.closest("input, textarea, select")) return;

      const { clientX, clientY } = e;

      const spawn = () => {
        const attachRemove = (el) => {
          const done = () => {
            el.removeEventListener("animationend", done);
            el.remove();
          };
          el.addEventListener("animationend", done);
          document.body.appendChild(el);
        };

        const flash = document.createElement("div");
        flash.className = "cursor-ember-flash";
        flash.setAttribute("aria-hidden", "true");
        flash.style.left = `${clientX}px`;
        flash.style.top = `${clientY}px`;
        attachRemove(flash);

        /* Warm embers only — terracotta / coal family (no cool greens / “sparkle” hues) */
        const emberColors = [
          "var(--color-terracotta)",
          "var(--color-coal)",
          "color-mix(in srgb, var(--color-terracotta) 58%, var(--color-coal))",
          "color-mix(in srgb, var(--color-coal) 52%, var(--color-terracotta))",
        ];

        const count = 8 + Math.floor(Math.random() * 5);

        for (let i = 0; i < count; i += 1) {
          const el = document.createElement("div");
          el.className = "cursor-ember";
          el.setAttribute("aria-hidden", "true");
          el.style.left = `${clientX}px`;
          el.style.top = `${clientY}px`;

          const angle = Math.random() * Math.PI * 2;
          const dist =
            (i % 3 === 0 ? 8 + Math.random() * 14 : 22 + Math.random() * 34) +
            Math.random() * 8;
          el.style.setProperty("--dx", `${Math.cos(angle) * dist}px`);
          el.style.setProperty("--dy", `${Math.sin(angle) * dist}px`);

          const size = 4 + Math.floor(Math.random() * 4);
          el.style.width = `${size}px`;
          el.style.height = `${size}px`;
          const fg = emberColors[Math.floor(Math.random() * emberColors.length)];
          el.style.setProperty("--ember-fg", fg);
          el.style.animationDuration = `${0.48 + Math.random() * 0.14}s`;

          attachRemove(el);
        }
      };

      requestAnimationFrame(spawn);
    };

    layout.addEventListener("pointerdown", onPointerDown);
    return () => layout.removeEventListener("pointerdown", onPointerDown);
  }, []);

  return null;
}
