import React from "react";
import ReactDOM from "react-dom/client";
import "@/themes.css";
import "@/index.css";
import "@/theme-overrides.css";
import App from "@/App";
import { installFetchCredentials } from "@/lib/fetchCredentials";
import { initTheme } from "@/lib/theme";

installFetchCredentials();
initTheme();

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
