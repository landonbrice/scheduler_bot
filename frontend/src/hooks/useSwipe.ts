import { useRef } from "react";

export interface SwipeCallbacks {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  threshold?: number;
}

export function useSwipe({ onSwipeLeft, onSwipeRight, threshold = 60 }: SwipeCallbacks) {
  const startX = useRef<number | null>(null);
  const startY = useRef<number | null>(null);
  const canceled = useRef(false);

  return {
    onTouchStart: (e: React.TouchEvent) => {
      startX.current = e.touches[0].clientX;
      startY.current = e.touches[0].clientY;
      canceled.current = false;
    },
    onTouchMove: (e: React.TouchEvent) => {
      if (startX.current === null || startY.current === null) return;
      const dx = e.touches[0].clientX - startX.current;
      const dy = e.touches[0].clientY - startY.current;
      if (Math.abs(dy) > 2 * Math.abs(dx)) canceled.current = true;
    },
    onTouchEnd: (e: React.TouchEvent) => {
      if (startX.current === null || startY.current === null) return;
      const dx = e.changedTouches[0].clientX - startX.current;
      const dy = e.changedTouches[0].clientY - startY.current;
      startX.current = startY.current = null;
      if (canceled.current) return;
      if (Math.abs(dy) > Math.abs(dx)) return;
      if (dx <= -threshold) onSwipeLeft?.();
      else if (dx >= threshold) onSwipeRight?.();
    },
  };
}
