import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

export function DeferredContent({
  children,
  label = "City prices and market details",
  action = "Explore city prices",
}: {
  children: () => ReactNode;
  label?: string;
  action?: string;
}) {
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  const container = useRef<HTMLDivElement>(null);
  function reveal() {
    if (container.current?.contains(document.activeElement)) {
      container.current.focus({ preventScroll: true });
    }
    setVisible(true);
  }
  useEffect(() => {
    if (visible) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          if (container.current?.contains(document.activeElement))
            container.current.focus({ preventScroll: true });
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.05 },
    );
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [visible]);
  return (
    <div
      ref={container}
      className="deferred-content"
      role="group"
      aria-label={label}
      tabIndex={-1}
      style={visible ? undefined : { minHeight: 1200 }}
      onFocusCapture={() => {
        if (!visible) reveal();
      }}
    >
      {visible ? children() : <button onClick={reveal}>{action}</button>}
    </div>
  );
}
