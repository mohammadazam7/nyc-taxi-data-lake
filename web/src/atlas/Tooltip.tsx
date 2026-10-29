import { useEffect, useRef, type ReactNode } from "react";
import { create } from "zustand";

interface TipState { content: ReactNode | null; x: number; y: number }
const useTip = create<TipState>(() => ({ content: null, x: 0, y: 0 }));

export const showTip = (x: number, y: number, content: ReactNode) => useTip.setState({ x, y, content });
export const hideTip = () => useTip.setState({ content: null });

/** One floating tooltip for the whole page, kept inside the viewport. */
export function TooltipLayer() {
  const { content, x, y } = useTip();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const left = Math.min(x + 14, window.innerWidth - el.offsetWidth - 8);
    const top = Math.min(y + 14, window.innerHeight - el.offsetHeight - 8);
    el.style.transform = `translate(${left}px, ${top}px)`;
  }, [x, y, content]);
  return (
    <div
      ref={ref}
      role="status"
      aria-live="polite"
      className={`pointer-events-none fixed left-0 top-0 z-50 max-w-xs rounded-[10px] border border-line bg-[rgba(12,16,26,0.96)] px-2.5 py-2 text-xs text-ink shadow-panel transition-opacity duration-100 ${content ? "opacity-100" : "opacity-0"}`}
    >
      {content}
    </div>
  );
}
