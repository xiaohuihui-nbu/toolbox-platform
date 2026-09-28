<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { useRoute, useRouter } from "vue-router";
import { useToolboxStore } from "../../store/modules/toolbox.store";
const SystemManagement = defineAsyncComponent(() => import("./SystemManagement.vue"));
import {
  ArrowDownToLine,
  ArrowRight,
  AudioLines,
  Bell,
  Binary,
  Blocks,
  Braces,
  Check,
  CheckCheck,
  ChevronDown,
  CircleHelp,
  Clock3,
  CloudUpload,
  Download,
  File,
  FileText,
  FolderOpen,
  Grid2X2,
  HardDrive,
  Headphones,
  Heart,
  Layers3,
  LoaderCircle,
  LogOut,
  Menu,
  Monitor,
  Moon,
  MoreHorizontal,
  Music2,
  Palette,
  Play,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Sun,
  Video,
  WandSparkles,
  X,
} from "lucide-vue-next";
import { api, ApiError, send } from "../../api/toolbox";
import MediaPreview from "../../components/toolbox/MediaPreview.vue";
import TaskCenter from "./TaskCenter.vue";
import DynamicForm from "../../components/toolbox/DynamicForm.vue";
import ResultRenderer from "../../components/toolbox/ResultRenderer.vue";
import VideoDownloader from "../../tool-views/VideoDownloader.vue";
import { useAppearance, type Mode, type Accent } from "../../composables/toolbox/useAppearance";

interface Tool {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  color: string;
  tags: string[];
  mode: string;
  note: string;
  enabled: boolean;
  input_schema: any;
}
interface Job {
  id: string;
  tool_id: string;
  title: string;
  state: string;
  progress: number;
  message: string;
  created_at: string;
  result: { asset_id?: string };
}
interface Asset {
  id: string;
  name: string;
  mime: string;
  size: number;
  created_at: string;
  preview_kind?: "audio" | "video" | null;
}
const previewAsset = ref<string | null>(null),
  submittedJob = ref<Job | null>(null);
const voices = ref<{ id: string; name: string; description: string }[]>([]),
  ttsState = ref("loading");
async function loadVoices() {
  ttsState.value = "loading";
  try {
    const [status, items] = await Promise.all([api("/tts/status"), api("/tts/voices")]);
    voices.value = items;
    ttsState.value = status.status;
  } catch {
    ttsState.value = "unavailable";
  }
}
const icons: Record<string, any> = {
  AudioLines,
  Download,
  Music2,
  FileText,
  Braces,
  Binary,
};
const { user } = storeToRefs(useToolboxStore());
const route = useRoute(), router = useRouter();
const systemManagement = ref(false);
const loaded = ref(false),
  busy = ref(false),
  mobileNav = ref(false);
const tools = ref<Tool[]>([]),
  jobs = ref<Job[]>([]),
  assets = ref<Asset[]>([]);
const stats = ref<any>({
  jobs: {},
  file_count: 0,
  storage_bytes: 0,
  storage_limit: 2147483648,
});
const nav = computed(() => String(route.params.section || "home")),
  category = ref("全部工具"),
  search = ref(""),
  searchInput = ref<HTMLInputElement>();
const toast = ref(""),
  apiOnline = ref(true),
  lastSync = ref("");
const login = reactive({ username: "admin", password: "" });
const form = reactive<Record<string, any>>({}),
  selected = ref<Tool | null>(null),
  selectedJob = ref<Job | null>(null);
const output = ref(""),
  formError = ref(""),
  fileBusy = ref(false),
  submitted = ref(false);
const loginError = ref(""),
  authBusy = ref(false),
  page = ref(1),
  assetPage = ref(1);
const userForm = reactive({ username: "", name: "", password: "" });
const passwordForm = reactive({ current_password: "", new_password: "" });
const { mode, accent, favorites, restorePreferences, toggleFavorite } = useAppearance(user, notify);
const stateLabels: Record<string, string> = {
  queued: "等待中",
  running: "处理中",
  cancel_requested: "取消中",
  reconciling: "待核对",
  succeeded: "已完成",
  failed: "未完成",
  cancelled: "已取消",
};
const navItems = [
  { id: "home", title: "工具工作台", icon: Grid2X2 },
  { id: "favorites", title: "我的收藏", icon: Heart },
  { id: "jobs", title: "任务中心", icon: Layers3 },
  { id: "files", title: "文件中心", icon: FolderOpen },
];
const enabledTools = computed(() => tools.value.filter((tool) => tool.enabled));
const visibleFavorites = computed(() =>
  enabledTools.value.filter((tool) => favorites.value.includes(tool.id))
);
const featuredTts = computed(() => enabledTools.value.find((tool) => tool.id === "tts.natural"));
const featuredVideo = computed(() =>
  enabledTools.value.find((tool) => tool.id === "video.download")
);
const filtered = computed(() =>
  enabledTools.value.filter(
    (t) =>
      (category.value === "全部工具" || t.category === category.value) &&
      (nav.value !== "favorites" || favorites.value.includes(t.id)) &&
      `${t.name} ${t.description} ${t.tags.join(" ")}`
        .toLowerCase()
        .includes(search.value.toLowerCase())
  )
);
const categories = computed(() => [
  "全部工具",
  ...new Set(enabledTools.value.map((t) => t.category)),
]);
watch(categories, (available) => {
  if (!available.includes(category.value)) category.value = "全部工具";
});
const activeCount = computed(
  () =>
    (stats.value.jobs.running || 0) +
    (stats.value.jobs.queued || 0) +
    (stats.value.jobs.cancel_requested || 0)
);
const pageTitle = computed(() => navItems.find((n) => n.id === nav.value)?.title || "偏好设置");
const schemaFields = computed(
  () => Object.entries(selected.value?.input_schema?.properties || {}) as [string, any][]
);
const hasNextJobs = computed(() => jobs.value.length === 50),
  hasNextAssets = computed(() => assets.value.length === 50);
let poll: ReturnType<typeof setInterval>, toastTimer: ReturnType<typeof setTimeout>;
let lastFocus: HTMLElement | null = null;
const modalRef = ref<HTMLElement>();

function notify(message: string) {
  toast.value = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toast.value = ""), 4200);
}
function go(target: string) {
  router.push(`/${target}`);
  search.value = "";
  category.value = "全部工具";
  mobileNav.value = false;
}
function formatBytes(n: number) {
  return n < 1024
    ? `${n} B`
    : n < 1048576
      ? `${(n / 1024).toFixed(1)} KB`
      : n < 1073741824
        ? `${(n / 1048576).toFixed(1)} MB`
        : `${(n / 1073741824).toFixed(2)} GB`;
}
function formatTime(s: string) {
  return new Date(`${s}Z`).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
async function refresh() {
  if (!user.value || document.hidden) return;
  try {
    const results = await Promise.all([
      api<Job[]>(`/jobs?page=${page.value}`),
      api<Asset[]>(`/assets?page=${assetPage.value}`),
      api("/stats"),
      api<Tool[]>("/tools"),
    ]);
    [jobs.value, assets.value, stats.value, tools.value] = results;
    if (selectedJob.value) selectedJob.value = await api<Job>(`/jobs/${selectedJob.value.id}`);
    if (
      selected.value &&
      submittedJob.value &&
      !["succeeded", "failed", "cancelled"].includes(submittedJob.value.state)
    )
      submittedJob.value = await api<Job>(`/jobs/${submittedJob.value.id}`);
    apiOnline.value = true;
    lastSync.value = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch (e) {
    apiOnline.value = false;
    if (e instanceof ApiError && e.status === 401) {
      user.value = null;
      loginError.value = "会话已过期，请重新登录";
    }
  }
}
async function loadData() {
  await refresh();
}
async function signIn() {
  authBusy.value = true;
  loginError.value = "";
  try {
    user.value = await api("/auth/login", send("POST", login));
    login.password = "";
    restorePreferences();
    await loadData();
  } catch (e) {
    loginError.value = (e as Error).message;
  } finally {
    authBusy.value = false;
  }
}
async function signOut() {
  try {
    await api("/auth/logout", send("POST"));
    user.value = null;
  } catch (e) {
    notify((e as Error).message);
  }
}
async function openTool(tool: Tool) {
  if (!tool.enabled) return notify("此工具已被管理员停用");
  lastFocus = document.activeElement as HTMLElement;
  selected.value = tool;
  output.value = "";
  formError.value = "";
  submitted.value = false;
  submittedJob.value = null;
  if (tool.id === "tts.natural") void loadVoices();
  for (const key of Object.keys(form)) delete form[key];
  for (const [key, field] of Object.entries(tool.input_schema?.properties || {}) as [string, any][])
    form[key] = field.default ?? "";
  form.text ||= "";
  await nextTick();
  modalRef.value?.querySelector<HTMLElement>("textarea, input, select, button")?.focus();
}
function closeTool() {
  if (busy.value || fileBusy.value) return;
  selected.value = null;
  lastFocus?.focus();
}
async function uploadFile(event: Event, assign = false) {
  const input = event.target as HTMLInputElement,
    file = input.files?.[0];
  if (!file) return;
  if (file.size > 100 * 1024 * 1024) {
    notify("单文件最大 100 MB");
    return;
  }
  fileBusy.value = true;
  try {
    const data = new FormData();
    data.append("file", file);
    const asset = await api<Asset>("/assets", { method: "POST", body: data });
    if (assign) form.asset_id = asset.id;
    assetPage.value = 1;
    await refresh();
    notify("文件已保存到文件中心");
  } catch (e) {
    notify((e as Error).message);
  } finally {
    fileBusy.value = false;
    input.value = "";
  }
}
let pendingKey = "",
  pendingPayload = "";
async function submitTool() {
  if (!selected.value || busy.value) return;
  busy.value = true;
  formError.value = "";
  const params = Object.fromEntries(schemaFields.value.map(([key]) => [key, form[key]]));
  const payload = JSON.stringify({ tool_id: selected.value.id, params });
  if (payload !== pendingPayload) {
    pendingKey = crypto.randomUUID();
    pendingPayload = payload;
  }
  try {
    submittedJob.value = await api<Job>("/jobs", {
      method: "POST",
      headers: { "Idempotency-Key": pendingKey },
      body: payload,
    });
    pendingPayload = "";
    page.value = 1;
    submitted.value = true;
    await refresh();
    notify("任务已提交，可在任务中心查看进度");
  } catch (e) {
    formError.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function transform(action: string) {
  formError.value = "";
  try {
    if (action === "format") output.value = JSON.stringify(JSON.parse(form.text), null, 2);
    else if (action === "minify") output.value = JSON.stringify(JSON.parse(form.text));
    else if (action === "encode")
      output.value = btoa(
        Array.from(new TextEncoder().encode(form.text), (b) => String.fromCharCode(b)).join("")
      );
    else
      output.value = new TextDecoder("utf-8", { fatal: true }).decode(
        Uint8Array.from(atob(form.text.trim()), (c) => c.charCodeAt(0))
      );
  } catch (e) {
    formError.value = `转换失败：${(e as Error).message}`;
  }
}
async function copyOutput() {
  try {
    await navigator.clipboard.writeText(output.value);
    notify("已复制结果");
  } catch {
    notify("浏览器限制了剪贴板访问，请选中结果后手动复制");
  }
}
async function jobAction(job: Job, action: "cancel" | "retry") {
  try {
    await api(`/jobs/${job.id}/${action}`, {
      ...send("POST"),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    await refresh();
    notify(action === "retry" ? "已创建重试任务" : "取消请求已受理");
  } catch (e) {
    notify((e as Error).message);
  }
}
async function addUser() {
  try {
    await api("/admin/users", send("POST", userForm));
    Object.assign(userForm, { username: "", name: "", password: "" });
    notify("成员账号已创建");
  } catch (e) {
    notify((e as Error).message);
  }
}
async function changePassword() {
  try {
    await api("/me/password", send("PUT", passwordForm));
    passwordForm.current_password = "";
    passwordForm.new_password = "";
    user.value = null;
    notify("密码已修改，请重新登录");
  } catch (e) {
    notify((e as Error).message);
  }
}
async function toggleTool(tool: Tool) {
  try {
    const enabled = !tool.enabled;
    await api(`/admin/tools/${tool.id}`, send("PUT", { enabled }));
    tools.value = tools.value.map((item) => (item.id === tool.id ? { ...item, enabled } : item));
  } catch (e) {
    notify((e as Error).message);
  }
}
function keyboard(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key === "k") {
    event.preventDefault();
    go("home");
    nextTick(() => searchInput.value?.focus());
  }
  if (event.key === "Escape") {
    previewAsset.value = null;
    closeTool();
    selectedJob.value = null;
    mobileNav.value = false;
  }
  if (event.key === "Tab" && selected.value && modalRef.value) {
    const nodes = Array.from(
      modalRef.value.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input, textarea, select, a[href]"
      )
    );
    const first = nodes[0],
      last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
  }
}
watch([page, assetPage], refresh);
onMounted(async () => {
  window.addEventListener("keydown", keyboard);
  try {
    user.value = await api("/me");
    restorePreferences();
    await loadData();
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401))
      loginError.value = "暂时无法连接服务，请确认容器已启动";
  } finally {
    loaded.value = true;
  }
  poll = setInterval(refresh, 3500);
});
onUnmounted(() => {
  clearInterval(poll);
  clearTimeout(toastTimer);
  window.removeEventListener("keydown", keyboard);
});
</script>

<template>
  <div v-if="!loaded" class="loading-screen">
    <div class="brand-mark"><Blocks :size="25" /></div>
    <LoaderCircle class="spin" />正在打开工作空间
  </div>
  <div v-else-if="!user" class="login-page">
    <section class="login-story">
      <div class="brand">
        <span class="brand-mark"><Blocks :size="24" /></span
        ><span>拾光 <small>TOOLBOX</small></span>
      </div>
      <div class="login-copy">
        <span class="eyebrow">YOUR EVERYDAY TOOLKIT</span>
        <h1>把繁琐留给工具，<br />把时间留给创造。</h1>
        <p>音频、视频、文字与开发工具，<br />在一个有条理的工作空间里，各就各位。</p>
        <div class="login-orbs"><AudioLines /><Braces /><Video /><FileText /></div>
      </div>
      <p class="login-foot">私有部署 · 插件扩展 · 为你的工作流而生</p>
    </section>
    <section class="login-form-wrap">
      <form class="login-form" @submit.prevent="signIn">
        <span class="section-kicker">欢迎回来</span>
        <h2>登录你的工作空间</h2>
        <p class="muted">让今天的工作，轻一点。</p>
        <label
          >账号<input
            v-model="login.username"
            autocomplete="username"
            required
            placeholder="请输入账号" /></label
        ><label
          >密码<input
            v-model="login.password"
            autocomplete="current-password"
            type="password"
            required
            placeholder="请输入密码"
        /></label>
        <p v-if="loginError" class="error" role="alert">{{ loginError }}</p>
        <button class="primary full" :disabled="authBusy">
          <LoaderCircle v-if="authBusy" class="spin" :size="17" />进入工作空间<ArrowRight
            :size="17"
          />
        </button>
        <p class="login-hint"><ShieldCheck :size="16" />初始管理员密码见项目根目录 .env 文件。</p>
      </form>
      <button
        class="login-theme icon-button"
        @click="mode = mode === 'dark' ? 'light' : 'dark'"
        aria-label="切换深浅色"
      >
        <Moon v-if="mode !== 'dark'" /><Sun v-else />
      </button>
    </section>
  </div>
  <div v-else class="app-shell">
    <div v-if="mobileNav" class="mobile-scrim" @click="mobileNav = false"></div>
    <aside class="sidebar" :class="{ open: mobileNav }">
      <a class="brand" href="#home" @click.prevent="go('home')"
        ><span class="brand-mark"><Blocks :size="24" /></span
        ><span>拾光 <small>TOOLBOX</small></span></a
      >
      <div class="workspace-chip">
        <span class="workspace-avatar">W</span>
        <div><strong>我的工作空间</strong><small>个人与小团队</small></div>
        <ShieldCheck :size="16" />
      </div>
      <p class="nav-caption">工作空间</p>
      <nav>
        <button
          v-for="item in navItems"
          :key="item.id"
          :class="{ active: nav === item.id }"
          @click="go(item.id)"
        >
          <component :is="item.icon" :size="19" /><span>{{ item.title }}</span
          ><span v-if="item.id === 'jobs' && activeCount" class="count-badge">{{
            activeCount
          }}</span
          ><span v-if="item.id === 'favorites' && visibleFavorites.length" class="nav-count">{{
            visibleFavorites.length
          }}</span>
        </button>
      </nav>
      <div class="sidebar-bottom">
        <div class="storage-widget">
          <div>
            <span><HardDrive :size="15" />我的存储</span
            ><small>{{ Math.round((stats.storage_bytes / stats.storage_limit) * 100) }}%</small>
          </div>
          <div class="progress-track">
            <i
              :style="{
                width: `${Math.min(100, (stats.storage_bytes / stats.storage_limit) * 100)}%`,
              }"
            ></i>
          </div>
          <p>
            {{ formatBytes(stats.storage_bytes) }}
            <span>/ {{ formatBytes(stats.storage_limit) }}</span>
          </p>
        </div>
        <nav>
          <button :class="{ active: nav === 'settings' }" @click="go('settings')">
            <Settings2 :size="19" />偏好设置
          </button>
        </nav>
        <div class="profile">
          <span class="avatar">{{ user.name.slice(0, 1) }}</span>
          <div>
            <strong>{{ user.name }}</strong
            ><small>{{ user.is_admin ? "空间管理员" : "空间成员" }}</small>
          </div>
          <button class="icon-button" title="退出登录" @click="signOut">
            <LogOut :size="17" />
          </button>
        </div>
      </div>
    </aside>
    <div class="main-wrap">
      <header class="topbar">
        <div class="breadcrumb">
          <button class="icon-button mobile-menu" aria-label="打开导航" @click="mobileNav = true">
            <Menu /></button
          ><span>工作空间</span><span class="slash">/</span><strong>{{ pageTitle }}</strong>
        </div>
        <div class="top-actions">
          <span class="connection" :class="{ offline: !apiOnline }"
            ><i></i>{{ apiOnline ? "服务已连接" : "连接中断" }}</span
          >
          <div class="top-divider"></div>
          <button
            class="icon-button"
            @click="mode = mode === 'dark' ? 'light' : 'dark'"
            :title="mode === 'dark' ? '切换浅色模式' : '切换深色模式'"
            :aria-label="mode === 'dark' ? '切换浅色模式' : '切换深色模式'"
          >
            <Sun v-if="mode === 'dark'" :size="19" /><Moon v-else :size="19" /></button
          ><button class="icon-button" title="外观设置" @click="go('settings')">
            <Palette :size="19" /></button
          ><span class="avatar small">{{ user.name.slice(0, 1) }}</span>
        </div>
      </header>
      <main>
        <template v-if="nav === 'home' || nav === 'favorites'">
          <div class="page-heading">
            <div>
              <div class="section-kicker">
                {{ nav === "favorites" ? "YOUR COLLECTION" : "MAKE ROOM FOR CREATIVITY" }}
              </div>
              <h1>
                {{ nav === "favorites" ? "喜欢的工具，随时就绪" : "好工具，让想法轻松发生"
                }}<span class="heading-dot">.</span>
              </h1>
              <p>
                {{
                  nav === "favorites"
                    ? "把常用的留下，让每次开始更简单。"
                    : "一个工作空间，装下你的日常所需。"
                }}
              </p>
            </div>
            <span class="version-pill"><Sparkles :size="14" />你的效率工具箱</span>
          </div>
          <div v-if="nav === 'home' && (featuredTts || featuredVideo)" class="featured-workspace">
            <section v-if="featuredTts" class="hero">
              <div class="hero-content">
                <span class="hero-tag"><AudioLines :size="14" />VOICE STUDIO · 自然配音</span>
                <h2>让文字，拥有声音。</h2>
                <p>输入灵感，生成音频。<br />从第一段旁白开始，把想法变成作品。</p>
                <button @click="openTool(featuredTts)">
                  试试文字转语音<ArrowRight :size="17" />
                </button>
              </div>
              <div class="hero-art" aria-hidden="true">
                <div class="orbit orbit-one"></div>
                <div class="orbit orbit-two"></div>
                <div class="audio-card">
                  <div class="audio-card-top">
                    <span class="audio-icon"><AudioLines :size="24" /></span>
                    <div>
                      <strong>一点灵感，无限可能</strong><small>CREATE SOMETHING GREAT</small>
                    </div>
                    <span class="audio-dots">•••</span>
                  </div>
                  <div class="waveform">
                    <i
                      v-for="n in 43"
                      :key="n"
                      :style="{
                        height: `${18 + ((n * 17 + n * n * 3) % 48)}px`,
                        opacity: n > 29 ? 0.28 : 1,
                      }"
                    ></i>
                  </div>
                  <div class="audio-card-bottom">
                    <span>文字 · 声音 · 创作</span>
                    <div class="audio-play"><Play :size="16" fill="currentColor" /></div>
                    <span>TTS</span>
                  </div>
                </div>
                <span class="floating-note note-one"><Sparkles :size="15" />灵感正在发生</span
                ><span class="floating-note note-two"><AudioLines :size="15" />多音色创作</span>
              </div>
            </section>
            <section v-if="featuredVideo" class="video-feature">
              <div class="video-feature-art" aria-hidden="true">
                <div class="film-frame back"><Video :size="32" /></div>
                <div class="film-frame front">
                  <Play :size="25" fill="currentColor" /><span>VIDEO</span>
                </div>
                <i></i>
              </div>
              <span class="feature-kicker"><Download :size="14" />VIDEO LIBRARY</span>
              <h2>发现好内容，<br />留住每一帧。</h2>
              <p>搜索、批量下载、在线预览。<br />把音视频整理进你的工作空间。</p>
              <button class="secondary" @click="openTool(featuredVideo)">
                打开视频下载<ArrowRight :size="16" />
              </button>
            </section>
          </div>
          <div v-if="nav === 'home'" class="studio-shortcuts" aria-label="工作空间快捷入口">
            <button @click="searchInput?.focus()">
              <span class="shortcut-icon"><Grid2X2 :size="20" /></span
              ><span
                ><strong>{{ enabledTools.length }} 个可用工具</strong
                ><small>从灵感到成果</small></span
              ><ArrowRight :size="15" />
            </button>
            <button @click="go('jobs')">
              <span class="shortcut-icon"><Layers3 :size="20" /></span
              ><span
                ><strong>{{ activeCount }} 个进行中任务</strong><small>查看进展与结果</small></span
              ><ArrowRight :size="15" />
            </button>
            <button @click="go('files')">
              <span class="shortcut-icon"><FolderOpen :size="20" /></span
              ><span
                ><strong>{{ stats.file_count }} 份文件</strong><small>集中预览与下载</small></span
              ><ArrowRight :size="15" />
            </button>
          </div>
          <div class="workspace-grid">
            <section class="tools-area">
              <div class="section-heading">
                <div>
                  <h2>
                    {{ nav === "favorites" ? "我的收藏" : "探索工具"
                    }}<span>{{ filtered.length }}</span>
                  </h2>
                  <p>专注一件小事，也能带来大不同。</p>
                </div>
                <div class="search-field">
                  <Search :size="17" /><input
                    ref="searchInput"
                    v-model="search"
                    placeholder="搜索工具…"
                    aria-label="搜索工具"
                  /><kbd>Ctrl K</kbd>
                </div>
              </div>
              <div class="category-tabs" role="tablist" aria-label="工具分类">
                <button
                  v-for="cat in categories"
                  :key="cat"
                  role="tab"
                  :aria-selected="category === cat"
                  :class="{ active: category === cat }"
                  @click="category = cat"
                >
                  {{ cat }}
                </button>
              </div>
              <div class="tool-grid">
                <article
                  v-for="tool in filtered"
                  :key="tool.id"
                  class="tool-card"
                  :class="{ disabled: !tool.enabled }"
                >
                  <div class="tool-card-top">
                    <div class="tool-icon" :class="tool.color">
                      <component :is="icons[tool.icon]" :size="25" />
                    </div>
                    <button
                      class="favorite-button"
                      :class="{ saved: favorites.includes(tool.id) }"
                      :title="favorites.includes(tool.id) ? '取消收藏' : '收藏工具'"
                      :aria-label="`${favorites.includes(tool.id) ? '取消收藏' : '收藏'}${tool.name}`"
                      :aria-pressed="favorites.includes(tool.id)"
                      @click="toggleFavorite(tool.id)"
                    >
                      <Heart
                        :size="17"
                        :fill="favorites.includes(tool.id) ? 'currentColor' : 'none'"
                      />
                    </button>
                  </div>
                  <button class="tool-title" @click="openTool(tool)">
                    {{ tool.name }}<ArrowRight :size="16" />
                  </button>
                  <p>{{ tool.description }}</p>
                  <div class="tool-card-footer">
                    <div>
                      <span v-for="tag in tool.tags" :key="tag">{{ tag }}</span>
                    </div>
                    <span v-if="!tool.enabled" class="disabled-label">已停用</span
                    ><span v-else class="card-dot"></span>
                  </div>
                </article>
              </div>
              <div v-if="!filtered.length" class="empty-state">
                <Search :size="36" />
                <h3>
                  {{ nav === "favorites" ? "还没有收藏工具" : "暂时没有匹配的工具" }}
                </h3>
                <p>
                  {{
                    nav === "favorites"
                      ? "这里展示已启用的收藏工具；停用工具重新启用后会自动恢复。"
                      : "试试其他关键词，或切换工具分类。"
                  }}
                </p>
                <button class="secondary" @click="go('home')">查看全部工具</button>
              </div>
              <div class="extension-strip">
                <span class="extension-icon"><Blocks :size="22" /></span>
                <div>
                  <strong>工具持续生长，工作流随你而变</strong>
                  <p>统一插件接口，为更多音视频与 AI 能力留好位置。</p>
                </div>
                <span class="tiny-pill">可扩展</span>
              </div>
            </section>
            <aside class="activity-panel">
              <div class="section-heading compact">
                <h2>工作概览</h2>
                <span class="today-badge">当前空间</span>
              </div>
              <div class="overview-card">
                <div class="overview-main">
                  <span class="overview-icon"><CheckCheck :size="21" /></span>
                  <div>
                    <strong>{{ stats.jobs.succeeded || 0 }}<small>个</small></strong>
                    <p>已完成任务</p>
                  </div>
                  <span class="overview-spark">↗</span>
                </div>
                <div class="overview-row">
                  <span><i class="small-dot orange"></i>进行中</span
                  ><strong>{{ activeCount }}<small>个任务</small></strong>
                </div>
                <div class="overview-row">
                  <span><i class="small-dot blue-dot"></i>文件中心</span
                  ><strong>{{ stats.file_count }}<small>个文件</small></strong>
                </div>
              </div>
              <div class="section-heading compact recent-title">
                <h2>最近任务</h2>
                <button class="text-link" @click="go('jobs')">全部<ArrowRight :size="13" /></button>
              </div>
              <div v-if="jobs.length" class="recent-list">
                <button
                  v-for="job in jobs.slice(0, 4)"
                  :key="job.id"
                  class="recent-item"
                  @click="selectedJob = job"
                >
                  <span class="recent-icon"
                    ><component
                      :is="icons[tools.find((t) => t.id === job.tool_id)?.icon || 'FileText']"
                      :size="18" /></span
                  ><span
                    ><strong>{{ job.title }}</strong
                    ><small>{{ formatTime(job.created_at) }}</small></span
                  ><i class="status-dot" :class="job.state"></i>
                </button>
              </div>
              <div v-else class="recent-empty">
                <Clock3 :size="25" />
                <p>新的开始，空白也很好</p>
                <small>提交第一个任务后，<br />它的进度会出现在这里。</small>
              </div>
              <div class="tip-card">
                <span><WandSparkles :size="18" />效率小贴士</span>
                <p>常用的工具点个「收藏」，<br />下次打开，灵感不用等。</p>
                <div><span></span><i></i><i></i></div>
              </div>
              <div class="privacy-note"><ShieldCheck :size="14" />你的文件，保存在自己的空间</div>
            </aside>
          </div>
        </template>
        <TaskCenter
          v-else-if="nav === 'jobs'"
          :tools="tools"
          :user-id="user.id"
          @open-tool="openTool"
          @changed="refresh"
        />
        <template v-else-if="nav === 'files'">
          <div class="page-heading">
            <div>
              <div class="section-kicker">YOUR FILE LIBRARY</div>
              <h1>每一份成果，妥善安放<span class="heading-dot">.</span></h1>
              <p>集中管理上传文件与工具生成的结果。</p>
            </div>
            <label class="primary upload-label"
              ><LoaderCircle v-if="fileBusy" class="spin" :size="17" /><CloudUpload
                v-else
                :size="17" />上传文件<input
                type="file"
                :disabled="fileBusy"
                @change="uploadFile($event)"
            /></label>
          </div>
          <div class="file-banner">
            <div>
              <FolderOpen :size="28" /><span
                ><strong>{{ stats.file_count }} 个文件</strong
                ><small
                  >已使用 {{ formatBytes(stats.storage_bytes) }} /
                  {{ formatBytes(stats.storage_limit) }}</small
                ></span
              >
            </div>
            <span class="muted">单文件最大 100 MB · 私有存储</span>
          </div>
          <div v-if="assets.length" class="file-grid">
            <article v-for="asset in assets" :key="asset.id" class="file-card">
              <button
                class="file-preview"
                :aria-label="`预览 ${asset.name}`"
                @click="previewAsset = asset.id"
              >
                <AudioLines v-if="asset.mime.startsWith('audio/')" :size="42" /><Video
                  v-else-if="asset.mime.startsWith('video/')"
                  :size="42"
                /><FileText v-else :size="42" />
              </button>
              <h3 :title="asset.name">{{ asset.name }}</h3>
              <p>
                {{ formatBytes(asset.size) }}<span>{{ formatTime(asset.created_at) }}</span>
              </p>
              <button
                v-if="asset.preview_kind"
                class="secondary full"
                @click="previewAsset = asset.id"
              >
                <Play :size="16" />{{ asset.preview_kind === "audio" ? "试听音频" : "预览视频" }}
              </button>
              <a :href="`/api/assets/${asset.id}/download`" class="secondary"
                ><ArrowDownToLine :size="16" />下载文件</a
              >
            </article>
          </div>
          <div v-else class="empty-state bordered">
            <FolderOpen :size="42" />
            <h3>这里将收纳你的每一份成果</h3>
            <p>上传文件，或运行一个工具，文件会自动归集到这里。</p>
          </div>
          <div class="pagination">
            <button :disabled="assetPage <= 1" @click="assetPage--">上一页</button
            ><span>第 {{ assetPage }} 页</span
            ><button :disabled="!hasNextAssets" @click="assetPage++">下一页</button>
          </div>
        </template>
        <template v-else>
          <div class="page-heading">
            <div>
              <div class="section-kicker">MAKE IT YOURS</div>
              <h1>舒服的界面，顺手的日常<span class="heading-dot">.</span></h1>
              <p>选择你喜欢的外观，让工作空间更像自己。</p>
            </div>
            <span class="tiny-pill">自动保存</span>
          </div>
          <div class="settings-grid">
            <section class="settings-panel">
              <h2><Monitor :size="20" />外观模式</h2>
              <p>浅色、深色，或跟随系统的节奏。</p>
              <div class="mode-options">
                <button
                  v-for="(label, key) in {
                    light: '浅色模式',
                    dark: '深色模式',
                    system: '跟随系统',
                  }"
                  :key="key"
                  :class="{ selected: mode === key }"
                  @click="mode = key as Mode"
                >
                  <div class="mode-preview" :class="key">
                    <i></i>
                    <div><span></span><b></b><b></b></div>
                  </div>
                  <span
                    ><Sun v-if="key === 'light'" :size="16" /><Moon
                      v-else-if="key === 'dark'"
                      :size="16" /><Monitor v-else :size="16" />{{ label
                    }}<Check v-if="mode === key" :size="16"
                  /></span>
                </button>
              </div>
              <h2 class="theme-subtitle"><Palette :size="20" />主题配色</h2>
              <p>小小的色彩，给每天一点不同。</p>
              <div class="accent-options">
                <button
                  v-for="(label, key) in {
                    coral: '日落珊瑚',
                    blue: '晴空蔚蓝',
                    green: '薄荷森林',
                    violet: '暮色鸢尾',
                  }"
                  :key="key"
                  :aria-pressed="accent === key"
                  :class="{ selected: accent === key }"
                  @click="accent = key as Accent"
                >
                  <span :class="key"><Check v-if="accent === key" :size="19" /></span>{{ label }}
                </button>
              </div>
            </section>
            <section class="settings-panel environment-panel">
              <h2><ShieldCheck :size="20" />我的空间</h2>
              <div>
                <span>当前账号</span><strong>{{ user.username }}</strong>
              </div>
              <div>
                <span>账号角色</span><strong>{{ user.is_admin ? "管理员" : "成员" }}</strong>
              </div>
              <div>
                <span>已注册工具</span><strong>{{ tools.length }} 个</strong>
              </div>
              <div><span>应用版本</span><strong>0.2.0 · FastapiAdmin</strong></div>
              <div><span>文件可见范围</span><strong>仅本人</strong></div>
              <p class="settings-tip">外观设置会保存在当前账号，下次登录时自动恢复。</p>
            </section>
            <section class="settings-panel">
              <h2>修改密码</h2>
              <p>修改后会退出当前账号的所有会话。</p>
              <form @submit.prevent="changePassword" class="stacked-form">
                <label
                  >当前密码<input
                    type="password"
                    v-model="passwordForm.current_password"
                    autocomplete="current-password"
                    required /></label
                ><label
                  >新密码<input
                    type="password"
                    v-model="passwordForm.new_password"
                    autocomplete="new-password"
                    minlength="8"
                    maxlength="128"
                    required
                    placeholder="至少 8 位" /></label
                ><button class="secondary">更新密码</button>
              </form>
            </section>
            <section v-if="user.is_admin" class="settings-panel">
              <h2>邀请团队成员</h2>
              <p>为内网团队创建独立账号，每位成员拥有自己的任务与文件。</p>
              <button class="secondary" @click="systemManagement = true">用户、角色与审计管理</button>
              <a class="primary" href="/admin/" style="display:inline-flex;align-items:center;justify-content:center;text-decoration:none">打开 FastapiAdmin 后台</a>
              <form @submit.prevent="addUser" class="stacked-form">
                <label
                  >账号<input
                    v-model="userForm.username"
                    pattern="[a-zA-Z][a-zA-Z0-9_.-]{2,31}"
                    required
                    placeholder="字母开头，3–32 位字母、数字或 _ . -" /></label
                ><label>显示名称<input v-model="userForm.name" required maxlength="32" /></label
                ><label
                  >初始密码<input
                    type="password"
                    v-model="userForm.password"
                    minlength="12"
                    maxlength="128"
                    required
                    autocomplete="new-password"
                    placeholder="至少 12 位" /></label
                ><button class="secondary"><Plus :size="16" />创建成员</button>
              </form>
            </section>
            <section v-if="user.is_admin" class="settings-panel tool-settings">
              <h2>工具管理</h2>
              <p>停用后从工具页面和收藏中隐藏，并禁止新的服务端任务提交；已提交任务和文件保留。</p>
              <div v-for="tool in tools" :key="tool.id" class="tool-setting-row">
                <span class="mini-icon"><component :is="icons[tool.icon]" :size="20" /></span>
                <div>
                  <strong>{{ tool.name }}</strong
                  ><small>{{ tool.id }} · v1.0.0</small>
                </div>
                <button
                  class="toggle"
                  role="switch"
                  :aria-checked="tool.enabled"
                  :aria-label="`${tool.name}启用状态`"
                  :class="{ on: tool.enabled }"
                  @click="toggleTool(tool)"
                >
                  <i></i>
                </button>
              </div>
            </section>
          </div>
        </template>
        <footer class="page-footer">
          <span>拾光 TOOLBOX <i>·</i> 让工具回归简单</span
          ><span>为创造留一点时间 <Sparkles :size="13" /></span>
        </footer>
      </main>
    </div>
  </div>
  <SystemManagement v-if="user?.is_admin && systemManagement" v-model="systemManagement" />
  <div v-if="selected" class="modal-backdrop" @click.self="closeTool">
    <section
      ref="modalRef"
      class="tool-modal"
      :class="{ 'download-modal': selected.id === 'video.download' }"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tool-title"
    >
      <div class="modal-heading">
        <div class="tool-icon" :class="selected.color">
          <component :is="icons[selected.icon]" :size="25" />
        </div>
        <div>
          <h2 id="tool-title">{{ selected.name }}</h2>
          <p>{{ selected.description }}</p>
        </div>
        <button
          class="icon-button"
          aria-label="关闭工具"
          :disabled="busy || fileBusy"
          @click="closeTool"
        >
          <X :size="20" />
        </button>
      </div>
      <div v-if="selected.id !== 'video.download'" class="modal-note">
        <CircleHelp :size="16" /><span>{{ selected.note }}</span>
      </div>
      <ResultRenderer
        v-if="submitted"
        :job="submittedJob"
        :state-labels="stateLabels"
        @open-jobs="
          closeTool();
          go('jobs');
        "
      />
      <VideoDownloader
        v-else-if="selected.id === 'video.download'"
        @created="refresh"
        @open-files="
          closeTool();
          go('files');
        "
      />
      <DynamicForm
        v-else-if="selected.mode === 'job'"
        :selected="selected"
        :form="form"
        :schema-fields="schemaFields"
        :voices="voices"
        :assets="assets"
        :tts-state="ttsState"
        :busy="busy"
        :file-busy="fileBusy"
        :form-error="formError"
        @submit="submitTool"
        @refresh-voices="loadVoices"
        @upload="uploadFile($event, true)"
      />
      <div v-else class="tool-form">
        <label
          >输入内容<textarea
            v-model="form.text"
            rows="7"
            placeholder="在这里粘贴内容…"
            spellcheck="false"
          ></textarea>
        </label>
        <div class="local-actions">
          <template v-if="selected.id === 'json.format'"
            ><button class="primary" @click="transform('format')">
              <Braces :size="16" />格式化</button
            ><button class="secondary" @click="transform('minify')">压缩</button></template
          ><template v-else
            ><button class="primary" @click="transform('encode')">编码</button
            ><button class="secondary" @click="transform('decode')">解码</button></template
          >
        </div>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <label v-if="output"
          >处理结果<textarea readonly :value="output" rows="8" spellcheck="false"></textarea></label
        ><button v-if="output" class="secondary" @click="copyOutput">复制结果</button>
      </div>
    </section>
  </div>
  <div v-if="selectedJob" class="modal-backdrop" @click.self="selectedJob = null">
    <section
      class="tool-modal job-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="job-title"
    >
      <div class="modal-heading">
        <div>
          <h2 id="job-title">{{ selectedJob.title }}</h2>
          <p>{{ selectedJob.id }}</p>
        </div>
        <button class="icon-button" aria-label="关闭任务详情" @click="selectedJob = null">
          <X />
        </button>
      </div>
      <span class="status" :class="selectedJob.state"
        ><i></i>{{ stateLabels[selectedJob.state] }}</span
      >
      <p class="job-message">{{ selectedJob.message }}</p>
      <MediaPreview v-if="selectedJob.result.asset_id" :asset-id="selectedJob.result.asset_id" />
      <p class="muted">创建于 {{ formatTime(selectedJob.created_at) }}</p>
      <div class="modal-footer">
        <span>进度 {{ selectedJob.progress }}%</span
        ><a
          v-if="selectedJob.result.asset_id"
          class="primary"
          :href="`/api/assets/${selectedJob.result.asset_id}/download`"
          ><Download :size="16" />下载结果</a
        ><button
          v-else
          class="secondary"
          @click="
            selectedJob = null;
            go('jobs');
          "
        >
          前往任务中心
        </button>
      </div>
    </section>
  </div>
  <div v-if="previewAsset" class="modal-backdrop" @click.self="previewAsset = null">
    <section class="tool-modal preview-modal" role="dialog" aria-modal="true" aria-label="文件预览">
      <div class="modal-heading">
        <h2>文件预览</h2>
        <button class="icon-button" aria-label="关闭预览" @click="previewAsset = null">
          <X :size="20" />
        </button>
      </div>
      <MediaPreview :asset-id="previewAsset" />
    </section>
  </div>
  <div v-if="toast" class="toast" role="status"><Check :size="17" />{{ toast }}</div>
</template>
