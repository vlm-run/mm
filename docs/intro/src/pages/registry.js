import { lazy } from "react";

const pages = [
  {
    id: "landing",
    label: "Intro",
    tag: "home",
    component: lazy(() => import("./Landing")),
  },
  {
    id: "cookbook",
    label: "Cookbook",
    tag: "guide",
    component: lazy(() => import("./Cookbook")),
  },
];

export default pages;
