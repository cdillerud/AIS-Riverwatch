import React from "react";
import ReactDOM from "react-dom/client";
import "@/themes.css";
import "@/index.css";
import "@/theme-overrides.css";
import App from "@/App";
import { installFetchCredentials } from "@/lib/fetchCredentials";
import { initTheme } from "@/lib/theme";
import { installConnectivityWatch } from "@/lib/connectivity";

installFetchCredentials();
installConnectivityWatch();   // after the credentials wrapper; feeds the offline hint
initTheme();

// Offline app shell + saved lock board (public/sw.js). Production builds only:
// a service worker in dev would serve stale bundles between edits.
if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((e) => console.warn("Service worker not registered:", e));
  });
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
