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
    tag: "",
    component: lazy(() => import("./GettingStarted")),
  },
  {
    id: "cookbook",
    label: "Cookbook",
    tag: "",
    component: lazy(() => import("./Cookbook")),
  },
];

export default pages;
