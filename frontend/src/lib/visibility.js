// Polling helpers: a backgrounded tab or phone kept polling every endpoint
// at full rate (~18 requests/min per open dashboard). Interval callbacks wrap
// their work in whenVisible; onVisible refreshes as soon as the tab is back.

export function pageHidden() {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

export function whenVisible(fn) {
  return (...args) => {
    if (!pageHidden()) return fn(...args);
    return undefined;
  };
}

// Call fn when the page becomes visible again; returns the unsubscribe.
export function onVisible(fn) {
  if (typeof document === "undefined") return () => {};
  const h = () => { if (!pageHidden()) fn(); };
  document.addEventListener("visibilitychange", h);
  return () => document.removeEventListener("visibilitychange", h);
}
