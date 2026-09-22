import { useEffect, useRef } from "react";

/** Keep native details keyboard behavior, with popover dismissal around it. */
export function useDismissibleDetails() {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (typeof document === "undefined") return;
    const outside = (event: PointerEvent) => {
      const menu = ref.current;
      if (!menu?.open || menu.contains(event.target as Node)) return;
      const target = event.target as Element | null;
      const tooltip = target?.closest?.('[role="tooltip"]') ?? target?.parentElement?.closest('[role="tooltip"]');
      if (tooltip?.id && Array.from(menu.querySelectorAll("[aria-describedby]")).some(trigger =>
        trigger.getAttribute("aria-describedby")?.split(/\s+/).includes(tooltip.id))) return;
      menu.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      const menu = ref.current;
      if (!menu?.open || event.key !== "Escape") return;
      menu.open = false;
      menu.querySelector<HTMLElement>(":scope > summary")?.focus();
      event.preventDefault();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  return ref;
}
