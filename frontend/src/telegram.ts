type WebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  HapticFeedback?: { impactOccurred: (s: "light" | "medium" | "heavy") => void };
  colorScheme: "light" | "dark";
};

declare global {
  interface Window { Telegram?: { WebApp: WebApp } }
}

export function tg(): WebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function initData(): string {
  return tg()?.initData ?? "";
}

export function haptic(kind: "light" | "medium" | "heavy" = "light") {
  tg()?.HapticFeedback?.impactOccurred(kind);
}
