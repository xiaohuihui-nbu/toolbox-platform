<script setup lang="ts">
import { computed, onUnmounted, ref } from "vue";
import {
  ArrowDownToLine,
  CircleHelp,
  ExternalLink,
  Link2,
  LoaderCircle,
  Play,
  Search,
  Video,
} from "lucide-vue-next";
import { api, send } from "../api/toolbox";
import AssetPreviewDialog from "../components/toolbox/AssetPreviewDialog.vue";
interface Item {
  url: string;
  title: string;
  uploader: string;
  duration: number | string | null;
  thumbnail?: string;
}
interface Receipt {
  url: string;
  state: string;
  message?: string;
  job?: any;
}
const emit = defineEmits<{ created: []; openFiles: [] }>();
const tab = ref("search"),
  query = ref(""),
  platform = ref("bilibili"),
  links = ref("");
const quality = ref("best");
const sourceSearchUrl = computed(() =>
  platform.value === "bilibili"
    ? `https://search.bilibili.com/all?keyword=${encodeURIComponent(query.value.trim())}`
    : `https://www.youtube.com/results?search_query=${encodeURIComponent(query.value.trim())}`
);
const searching = ref(false),
  submitting = ref(false),
  searched = ref(false),
  error = ref("");
const results = ref<Item[]>([]),
  selected = ref<string[]>([]),
  receipts = ref<Receipt[]>([]),
  preview = ref<string | null>(null);
const broken = ref<Record<string, boolean>>({}),
  searchId = ref("");
const accepted = computed(() => receipts.value.filter((item) => item.job).length);
const labels: Record<string, string> = {
  queued: "等待下载",
  running: "正在下载",
  succeeded: "已完成",
  failed: "下载失败",
  cancelled: "已取消",
  cancel_requested: "取消中",
};
const lines = computed(() =>
  links.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
);
function youtubeUrl(value: string) {
  try {
    const parsed = new URL(value);
    const host = parsed.hostname.toLowerCase();
    return ["http:", "https:"].includes(parsed.protocol) &&
      !parsed.username &&
      !parsed.password &&
      (host === "youtu.be" || host === "youtube.com" || host.endsWith(".youtube.com"))
      ? parsed.href
      : "";
  } catch {
    return "";
  }
}
const hasYoutube = computed(() =>
  tab.value === "search"
    ? platform.value === "youtube"
    : lines.value.some((url) => !!youtubeUrl(url))
);
let searchTimer: ReturnType<typeof setTimeout>,
  jobTimer: ReturnType<typeof setInterval>,
  alive = true;
let pendingPayload = "",
  pendingKey = "";
function duration(value: number | string | null) {
  if (typeof value === "string") return value;
  if (!value) return "时长未知";
  return `${Math.floor(value / 60)}:${String(Math.floor(value % 60)).padStart(2, "0")}`;
}
async function searchVideos() {
  if (!query.value.trim() || searching.value) return;
  searching.value = true;
  error.value = "";
  searched.value = true;
  results.value = [];
  selected.value = [];
  try {
    const data = await api(
      "/video-search",
      send("POST", {
        query: query.value.trim(),
        platform: platform.value,
        limit: 8,
      })
    );
    if (!alive) return;
    searchId.value = data.id;
    await pollSearch();
  } catch (e) {
    error.value = (e as Error).message;
    searching.value = false;
  }
}
async function pollSearch() {
  try {
    const data = await api(`/video-search/${searchId.value}`);
    if (!alive) return;
    if (data.state === "succeeded") {
      results.value = data.items;
      searching.value = false;
    } else if (data.state === "failed") {
      error.value = data.error;
      searching.value = false;
    } else searchTimer = setTimeout(pollSearch, 1500);
  } catch (e) {
    if (alive) {
      error.value = (e as Error).message;
      searching.value = false;
    }
  }
}
async function submitBatch() {
  const items =
    tab.value === "search"
      ? results.value
          .filter((item) => selected.value.includes(item.url))
          .map(({ url, title }) => ({ url, title: title.slice(0, 160) }))
      : lines.value.map((url) => ({ url, title: "" }));
  if (!items.length) return;
  if (items.length > 20) {
    error.value = "每批最多 20 条链接，请分批提交。";
    return;
  }
  error.value = "";
  submitting.value = true;
  const body = JSON.stringify({ items, quality: quality.value });
  if (body !== pendingPayload) {
    pendingPayload = body;
    pendingKey = crypto.randomUUID();
  }
  try {
    const data = await api("/video-downloads/batch", {
      method: "POST",
      headers: { "Idempotency-Key": pendingKey },
      body,
    });
    receipts.value = data.items;
    emit("created");
    await refreshJobs();
    clearInterval(jobTimer);
    jobTimer = setInterval(refreshJobs, 3000);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    submitting.value = false;
  }
}
async function refreshJobs() {
  if (
    !alive ||
    !receipts.value.some(
      (item) => item.job && ["queued", "running", "cancel_requested"].includes(item.job.state)
    )
  )
    return;
  try {
    const jobs = await api<any[]>("/jobs");
    if (!alive) return;
    const map = new Map(jobs.map((job) => [job.id, job]));
    receipts.value = receipts.value.map((item) =>
      item.job && map.has(item.job.id) ? { ...item, job: map.get(item.job.id) } : item
    );
    emit("created");
  } catch (e) {
    error.value = (e as Error).message;
  }
}
function chooseAll() {
  selected.value =
    selected.value.length === results.value.length ? [] : results.value.map((item) => item.url);
}
onUnmounted(() => {
  alive = false;
  clearTimeout(searchTimer);
  clearInterval(jobTimer);
});
</script>
<template>
  <div class="video-downloader">
    <div class="download-workflow" aria-label="下载步骤">
      <span><b>01</b>选择视频</span><i></i><span><b>02</b>设置画质</span><i></i
      ><span><b>03</b>下载与预览</span>
    </div>
    <div class="download-tabs">
      <button :class="{ active: tab === 'search' }" @click="tab = 'search'">
        <Search :size="16" />搜索视频</button
      ><button :class="{ active: tab === 'links' }" @click="tab = 'links'">
        <Link2 :size="16" />粘贴链接
      </button>
    </div>
    <button class="text-link" @click="emit('openFiles')">
      <Play :size="15" />查看已下载文件与播放预览
    </button>
    <aside v-if="hasYoutube" class="youtube-access-note" aria-label="YouTube 免登录说明">
      <CircleHelp :size="19" />
      <div>
        <strong>YouTube · 免登录尝试</strong>
        <p>
          公开视频也可能触发登录验证。当前按免登录方式尝试，遇到验证会停止并显示原因；浏览器登录态不会自动同步到服务器。
        </p>
      </div>
    </aside>
    <template v-if="tab === 'search'">
      <form class="video-search-bar" @submit.prevent="searchVideos">
        <select v-model="platform" aria-label="搜索平台" :disabled="searching">
          <option value="bilibili">哔哩哔哩</option>
          <option value="youtube">YouTube</option></select
        ><input
          v-model="query"
          aria-label="视频搜索关键词"
          placeholder="搜索你想下载的视频…"
          maxlength="120"
          required
          :disabled="searching"
        /><button class="primary" :disabled="searching">
          <LoaderCircle v-if="searching" class="spin" :size="16" /><Search v-else :size="16" />搜索
        </button>
      </form>
      <p class="field-hint">支持关键词搜索，勾选结果即可批量下载；每批最多 20 条。</p>
      <div v-if="searching" class="search-empty">
        <LoaderCircle class="spin" :size="27" />
        <p>正在搜索，请稍候…</p>
      </div>
      <div v-else-if="!results.length" class="search-empty">
        <Video :size="33" />
        <p>
          {{
            error
              ? "本次搜索未完成，请查看下方提示后重试。"
              : searched
                ? "暂未找到结果，试试其他关键词或平台。"
                : "从一个关键词，找到需要的视频"
          }}
        </p>
        <a
          v-if="error && query.trim()"
          class="text-link"
          :href="sourceSearchUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          <ExternalLink :size="14" />到{{
            platform === "bilibili" ? "B站" : "YouTube"
          }}搜索，复制链接后下载
        </a>
      </div>
      <template v-else
        ><div class="search-results-heading">
          <span>找到 {{ results.length }} 个结果</span
          ><button class="text-link" @click="chooseAll">
            {{ selected.length === results.length ? "取消全选" : "全选" }}
          </button>
        </div>
        <div class="video-search-grid">
          <article
            v-for="item in results"
            :key="item.url"
            class="video-search-card"
            :class="{ selected: selected.includes(item.url) }"
          >
            <label class="search-cover"
              ><img
                v-if="item.thumbnail && !broken[item.url]"
                :src="item.thumbnail"
                alt=""
                loading="lazy"
                @error="broken[item.url] = true"
              /><Video v-else :size="34" /><input
                type="checkbox"
                v-model="selected"
                :value="item.url"
                :aria-label="`选择 ${item.title}`"
              /><span>{{ duration(item.duration) }}</span></label
            >
            <div class="search-card-body">
              <h3 :title="item.title">{{ item.title }}</h3>
              <p>
                {{ item.uploader || "公开视频"
                }}<a
                  :href="item.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="打开视频原页面"
                  ><ExternalLink :size="14"
                /></a>
              </p>
            </div>
          </article></div
      ></template>
    </template>
    <template v-else
      ><label class="batch-links"
        >视频链接<textarea
          v-model="links"
          rows="6"
          placeholder="每行粘贴一个视频链接，最多 20 条"
          :disabled="submitting"
        ></textarea>
      </label>
      <p class="field-hint">
        已输入 {{ lines.length }} 条 · 自动跳过本批次完全相同的链接 · 每条分别执行
      </p></template
    >

    <label class="download-options"
      >下载清晰度
      <select v-model="quality" :disabled="submitting" aria-label="下载清晰度">
        <option value="best">最高可用画质</option>
        <option value="1080p">1080p 以内</option>
        <option value="720p">720p 以内 · 均衡推荐</option>
        <option value="480p">480p 以内 · 小文件</option>
      </select>
      <span class="field-hint">选择较低画质可减少下载体积，按源站可用格式选择，不额外转码。</span>
    </label>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="batch-toolbar">
      <span>{{
        tab === "search" ? `已选 ${selected.length} 个视频` : `待提交 ${lines.length} 条链接`
      }}</span
      ><button
        class="primary"
        :disabled="submitting || (tab === 'search' ? !selected.length : !lines.length)"
        @click="submitBatch"
      >
        <LoaderCircle v-if="submitting" class="spin" :size="16" /><ArrowDownToLine
          v-else
          :size="16"
        />{{ submitting ? "正在提交…" : "批量下载" }}
      </button>
    </div>
    <section v-if="receipts.length" class="batch-receipts">
      <h3>本次提交 · {{ accepted }} 个任务已受理</h3>
      <article v-for="(item, index) in receipts" :key="index">
        <div>
          <strong>{{ item.job?.title || `链接 ${index + 1}` }}</strong
          ><small :title="item.url">{{ item.url }}</small>
          <p v-if="item.message || item.job?.state === 'failed'" class="batch-error">
            {{ item.message || item.job?.message }}
          </p>
          <a
            v-if="item.job?.state === 'failed' && youtubeUrl(item.url)"
            class="source-video-link"
            :href="youtubeUrl(item.url)"
            target="_blank"
            rel="noopener noreferrer"
            ><ExternalLink :size="13" />在 YouTube 查看原视频</a
          >
        </div>
        <span class="status" :class="item.job?.state">{{
          item.job ? labels[item.job.state] : item.state === "duplicate" ? "已去重" : "未受理"
        }}</span
        ><button
          v-if="item.job?.result.asset_id"
          class="text-link"
          @click="preview = item.job.result.asset_id"
        >
          <Play :size="15" />预览
        </button>
      </article>
      <p class="field-hint">关闭窗口不影响后台下载；可在任务中心取消或重试单个任务。</p>
    </section>
    <AssetPreviewDialog v-if="preview" :asset-id="preview" @close="preview = null" />
  </div>
</template>
