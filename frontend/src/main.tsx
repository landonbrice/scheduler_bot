import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { tg } from "./telegram";
import "./index.css";

tg()?.ready();
tg()?.expand?.();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
