// TEMPORARY development-only entry — see index.html in this folder.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PetAssetAlignmentTest } from "./PetAssetAlignmentTest";
import "./alignment.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PetAssetAlignmentTest />
  </StrictMode>,
);
