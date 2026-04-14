import { lazy } from "react";

const pages = [
  {
    id: "landing",
    label: "Intro",
    tag: "home",
    component: lazy(() => import("./Landing")),
  },
  {
    id: "getting-started",
    label: "Getting Started",
    tag: "setup",
    component: lazy(() => import("./GettingStarted")),
  },
  {
    id: "cookbook",
    label: "Cookbook",
    tag: "guide",
    component: lazy(() => import("./Cookbook")),
  },
];

export default pages;
