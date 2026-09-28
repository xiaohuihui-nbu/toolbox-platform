import { onUnmounted, ref, watch, type Ref } from "vue";
import { api, send } from "../../api/toolbox";

export type Mode = "light" | "dark" | "system";
export type Accent = "coral" | "blue" | "green" | "violet";

/** Apply the local appearance immediately; serialize authenticated preference writes. */
export function useAppearance(user: Ref<any>, notify: (message: string) => void) {
  let cached: { mode?: Mode; accent?: Accent } = {};
  try {
    cached = JSON.parse(localStorage.getItem("tb:appearance") || "{}");
  } catch {
    /* Ignore malformed cache. */
  }
  const mode = ref<Mode>(
    cached.mode && ["light", "dark", "system"].includes(cached.mode) ? cached.mode : "dark"
  );
  const accent = ref<Accent>(
    cached.accent && ["coral", "blue", "green", "violet"].includes(cached.accent)
      ? cached.accent
      : "blue"
  );
  const favorites = ref<string[]>([]);
  const media = matchMedia("(prefers-color-scheme: dark)");
  let restoring = false;
  let queue: Promise<unknown> = Promise.resolve();

  function applyTheme() {
    document.documentElement.dataset.theme =
      mode.value === "system" ? (media.matches ? "dark" : "light") : mode.value;
    document.documentElement.dataset.accent = accent.value;
    localStorage.setItem(
      "tb:appearance",
      JSON.stringify({ mode: mode.value, accent: accent.value })
    );
  }
  async function save() {
    if (!user.value) return;
    const snapshot = {
      mode: mode.value,
      accent: accent.value,
      favorites: [...favorites.value],
    };
    try {
      queue = queue
        .catch(() => undefined)
        .then(() => api("/me/preferences", send("PUT", snapshot)));
      await queue;
    } catch (error) {
      notify(`偏好尚未同步：${(error as Error).message}`);
    }
  }
  function restorePreferences() {
    restoring = true;
    const preferences = user.value?.preferences;
    if (preferences?.mode) mode.value = preferences.mode;
    if (preferences?.accent) accent.value = preferences.accent;
    favorites.value = preferences?.favorites || [];
    restoring = false;
    applyTheme();
  }
  function toggleFavorite(id: string) {
    favorites.value = favorites.value.includes(id)
      ? favorites.value.filter((value) => value !== id)
      : [...favorites.value, id];
    void save();
  }
  watch(
    [mode, accent],
    () => {
      applyTheme();
      if (!restoring) void save();
    },
    { flush: "sync" }
  );
  applyTheme();
  media.addEventListener("change", applyTheme);
  onUnmounted(() => media.removeEventListener("change", applyTheme));
  return { mode, accent, favorites, restorePreferences, toggleFavorite };
}
