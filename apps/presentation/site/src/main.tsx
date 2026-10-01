import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { LhtbBrief } from "./LhtbBrief";
import { SweMarathonBrief } from "./SweMarathonBrief";
import "./styles.css";
import "./swe-marathon-brief.css";
import "./lhtb-brief.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("LoopX homepage root is missing");

const pathSegments = window.location.pathname.split("/").filter(Boolean);
if (pathSegments.at(-1) === "index.html") pathSegments.pop();
const isSweMarathonBrief = pathSegments.slice(-2).join("/") === "benchmarks/swe-marathon";
const isLhtbBrief = pathSegments.slice(-2).join("/") === "benchmarks/lhtb";

createRoot(rootElement).render(
  <StrictMode>
    {isSweMarathonBrief ? <SweMarathonBrief /> : isLhtbBrief ? <LhtbBrief /> : <App />}
  </StrictMode>,
);
