import { createApp, h } from "vue";
import { RouterView } from "vue-router";
import { createPlatformStore } from "./store/platform";
import { toolboxRouter } from "./router/toolbox";
import "./styles/toolbox.css";
const app = createApp({ render: () => h(RouterView) });
app.use(createPlatformStore());
app.use(toolboxRouter);
toolboxRouter.isReady().then(() => app.mount("#app"));

import "./styles/toolbox-tasks.css";
import "./styles/toolbox-studio.css";
import "./styles/toolbox-colors.css";
