// Send the session cookie with every backend API request.
//
// The backend authenticates via the `session_token` cookie. Browsers only send
// cookies cross-origin (e.g. dev: localhost:3000 -> :8001) when the request
// uses `credentials: 'include'`, so default that for API calls instead of
// editing every fetch() call site. An explicit `credentials` value is kept.
import { BACKEND_URL } from "@/lib/api";

function isApiRequest(url) {
  if (!url) return false;
  if (url.startsWith("/api/") || url === "/api") return true;
  return !!BACKEND_URL && url.startsWith(`${BACKEND_URL}/api`);
}

export function installFetchCredentials() {
  if (typeof window === "undefined" || !window.fetch || window.fetch.__riverwatchCreds) return;
  const originalFetch = window.fetch.bind(window);
  const wrapped = (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input?.url;
    if (isApiRequest(url) && !(init && init.credentials) && !(input instanceof Request)) {
      return originalFetch(input, { ...(init || {}), credentials: "include" });
    }
    return originalFetch(input, init);
  };
  wrapped.__riverwatchCreds = true;
  window.fetch = wrapped;
}
