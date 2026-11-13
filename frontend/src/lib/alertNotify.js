// Showing an alert: a system notification through the service worker
// (public/sw.js; Android Chrome only allows notifications from one), falling
// back to `new Notification` (desktop, dev builds without a worker).
//
// These are local notifications from the open (or backgrounded) app. With the
// app closed, the server sends Web Push instead (lib/push.js, public/sw.js).

export function notificationsSupported() {
  return typeof window !== "undefined" && "Notification" in window;
}

// "granted" | "denied" | "default" | "unsupported"
export function notificationPermission() {
  if (!notificationsSupported()) return "unsupported";
  return window.Notification.permission;
}

export async function requestNotificationPermission() {
  if (!notificationsSupported()) return "unsupported";
  try {
    const r = window.Notification.requestPermission();
    return (r && typeof r.then === "function") ? await r : window.Notification.permission;
  } catch {
    return window.Notification.permission;
  }
}

export async function showSystemNotification({ title, body, tag, sound = false }) {
  if (notificationPermission() !== "granted") return false;
  const opts = {
    body,
    tag,
    silent: !sound,
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: { url: "/dashboard" },
  };
  if (sound) opts.vibrate = [200, 100, 200];
  try {
    const reg = navigator.serviceWorker && await navigator.serviceWorker.getRegistration();
    if (reg && reg.showNotification) {
      await reg.showNotification(title, opts);
      return true;
    }
  } catch { /* fall through */ }
  try {
    // eslint-disable-next-line no-new
    new window.Notification(title, opts);
    return true;
  } catch {
    return false;
  }
}
