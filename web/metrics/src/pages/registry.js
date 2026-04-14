/**
 * Page registry — add new metric pages here.
 *
 * Each entry:
 *   id       — URL-safe slug (used as hash route)
 *   label    — Display name in sidebar nav
 *   tag      — Short category tag shown next to label
 *   component — lazy-loaded React component
 *
 * To add a new page:
 *   1. Create src/pages/MyPage.jsx (default export)
 *   2. Add an entry below
 *   3. Done — the router + nav pick it up automatically
 */
import { lazy } from "react";

const pages = [
  {
    id: "token-cost",
    label: "Token Cost",
    tag: "cost",
    component: lazy(() => import("./TokenCost")),
  },
  {
    id: "embedding-compare",
    label: "Embedding Compare",
    tag: "embed",
    component: lazy(() => import("./EmbeddingCompare")),
  },
];

export default pages;
