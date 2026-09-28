import { createRouter, createWebHashHistory } from "vue-router";
import Workspace from "../views/toolbox/Workspace.vue";

const sections = ["home", "favorites", "jobs", "files", "settings"];
const legacyHash = location.hash.slice(1);
if (sections.includes(legacyHash)) history.replaceState(null, "", `#/${legacyHash}`);

export const toolboxRouter = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", redirect: "/home" },
    { path: "/:section(home|favorites|jobs|files|settings)", component: Workspace },
    { path: "/:pathMatch(.*)*", redirect: "/home" },
  ],
});
