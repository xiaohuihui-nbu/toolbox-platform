import { createPinia } from "pinia";

/** Shared state foundation for the upstream admin and toolbox entry points. */
export const createPlatformStore = () => createPinia();
