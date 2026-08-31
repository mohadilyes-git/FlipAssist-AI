import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App, markShell } from "./App";
import "./styles.css";

markShell();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
