import { useEffect, useRef, useState } from "react";
import { API } from "@/lib/api";

// Google Identity Services: Google renders its own button, hands us a signed
// ID token, and the backend verifies it. Renders nothing (plus no divider) when
// the server has no GOOGLE_CLIENT_ID configured.

const GSI_SRC = "https://accounts.google.com/gsi/client";
let gsiPromise = null;
let configPromise = null;

function loadGsi() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!gsiPromise) {
    gsiPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => {
        gsiPromise = null;
        reject(new Error("Could not load Google sign-in"));
      };
      document.head.appendChild(script);
    });
  }
  return gsiPromise;
}

function loadAuthConfig() {
  if (!configPromise) {
    configPromise = fetch(`${API}/auth/config`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}))
      .then((cfg) => {
        if (!cfg.google_client_id) configPromise = null; // re-check next mount
        return cfg;
      });
  }
  return configPromise;
}

export default function GoogleSignInButton({ onCredential, onError, text = "continue_with", children }) {
  const buttonRef = useRef(null);
  const callbackRef = useRef(onCredential);
  const errorRef = useRef(onError);
  const [enabled, setEnabled] = useState(false);

  callbackRef.current = onCredential;
  errorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cfg = await loadAuthConfig();
      if (cancelled || !cfg.google_client_id) return;
      try {
        await loadGsi();
      } catch (err) {
        errorRef.current?.(err.message);
        return;
      }
      if (cancelled || !buttonRef.current) return;
      setEnabled(true);
      window.google.accounts.id.initialize({
        client_id: cfg.google_client_id,
        callback: (resp) => callbackRef.current?.(resp.credential),
        ux_mode: "popup",
      });
      const width = Math.min(400, buttonRef.current.offsetWidth || 320);
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "filled_black",
        size: "large",
        shape: "rectangular",
        text,
        width,
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [text]);

  return (
    <div style={enabled ? undefined : { display: "none" }}>
      <div ref={buttonRef} className="w-full flex justify-center mb-6" data-testid="google-signin-btn" />
      {children}
    </div>
  );
}
