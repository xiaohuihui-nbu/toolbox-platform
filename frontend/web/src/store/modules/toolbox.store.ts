import { defineStore } from "pinia";
import { ref } from "vue";

export const useToolboxStore = defineStore("toolbox", () => {
  // JWT remains in HttpOnly cookies; browser storage never receives credentials.
  const user = ref<any>(null);
  return { user };
});
