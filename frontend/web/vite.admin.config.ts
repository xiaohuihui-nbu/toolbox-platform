import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";
import ElementPlus from "unplugin-element-plus/vite";
import Icons from "unplugin-icons/vite";
import IconsResolver from "unplugin-icons/resolver";
import tailwindcss from "@tailwindcss/vite";
import autoprefixer from "autoprefixer";
import pkg from "./package.json";

const at = (path: string) => fileURLToPath(new URL(path, import.meta.url));
export default defineConfig({
  base: "/admin/",
  define: {
    // Interpret translation ASTs without Function/eval under the site's CSP.
    __INTLIFY_JIT_COMPILATION__: true,
    __APP_INFO__: JSON.stringify({ pkg, buildTimestamp: Date.now() }),
    "import.meta.env.VITE_TOOLBOX_ADMIN": JSON.stringify("true"),
    "import.meta.env.VITE_ACCESS_MODE": JSON.stringify("backend"),
    "import.meta.env.VITE_APP_BASE_API": JSON.stringify("/api/v1"),
  },
  resolve: { alias: Object.fromEntries(Object.entries({
    "@": "./src", "@views": "./src/views", "@imgs": "./src/assets/images",
    "@icons": "./src/assets/images/svg", "@utils": "./src/utils", "@stores": "./src/store",
    "@plugins": "./src/plugins", "@styles": "./src/styles", "@api": "./src/api", "@fa_imgs": "./src/assets/fa_imgs",
  }).map(([key, value]) => [key, at(value)])) },
  build: { outDir: "dist/admin", emptyOutDir: true, target: "es2022",
    rollupOptions: { input: at("./admin.html") }, chunkSizeWarningLimit: 2500 },
  plugins: [vue(), tailwindcss(), AutoImport({
    imports: ["vue", "vue-router", "pinia", "@vueuse/core", "vue-i18n",
      { axios: [["default", "axios"]] },
      { "element-plus/es": ["ElMessage", "ElMessageBox", "ElNotification", "ElScrollbar", "ElButton", "ElInput", "ElSwitch", "ElAvatar"] }],
    dirs: ["./src/hooks/core"], dts: false, vueTemplate: true, resolvers: [ElementPlusResolver(), IconsResolver()],
  }), Components({ dirs: ["src/components", "src/layouts", "src/**/components"],
    dts: false, resolvers: [ElementPlusResolver(), IconsResolver()] }),
    Icons({ autoInstall: false }), ElementPlus({ useSource: false })],
  css: { preprocessorMaxWorkers: 0, preprocessorOptions: { scss: { additionalData: '@use "@styles/core/mixin.scss" as *;' } },
    postcss: { plugins: [autoprefixer()] } },
});
