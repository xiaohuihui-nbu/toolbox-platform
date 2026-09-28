<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  Plus,
  Search,
  List,
  LayoutGrid,
  Columns3,
  X,
  Pencil,
  Trash2,
  RefreshCw,
  Play,
  Layers3,
} from "lucide-vue-next";
import { api, send } from "../../api/toolbox";
import MediaPreview from "../../components/toolbox/MediaPreview.vue";
import AssetPreviewDialog from "../../components/toolbox/AssetPreviewDialog.vue";

const props = defineProps<{ tools: any[]; userId: string }>();
const emit = defineEmits<{ openTool: [tool: any]; changed: [] }>();
const labels: Record<string, string> = {
  queued: "等待中",
  running: "处理中",
  cancel_requested: "取消中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
  reconciling: "待核对",
};
const modes = [
  { id: "list", name: "列表视图", icon: List },
  { id: "cards", name: "卡片视图", icon: LayoutGrid },
  { id: "board", name: "看板视图", icon: Columns3 },
];
const view = ref("list"),
  items = ref<any[]>([]),
  total = ref(0),
  page = ref(1);
const query = ref(""),
  state = ref(""),
  tool = ref(""),
  sort = ref("newest");
const error = ref(""),
  loading = ref(false),
  busy = ref(false),
  showCreate = ref(false);
const previewAsset = ref<string | null>(null);
const detail = ref<any>(null),
  editing = ref<any>(null),
  deleting = ref<any>(null);
const history = ref<any>(null);
const eventNames: Record<string, string> = { accepted: "已接收", running: "开始处理", succeeded: "处理完成", failed: "执行失败", cancelled: "已取消", cancel_requested: "申请取消", superseded: "参数更新", reconciling: "等待核对" };
const title = ref(""),
  params = ref(""),
  originalParams = ref("");
const editError = ref(""),
  deleteError = ref("");
const pageSize = 24;
const selected = ref<string[]>([]);
const batchDeleting = ref<any[] | null>(null);
const batchResult = ref<{
  deleted: number;
  skipped: { id: string; title: string; message: string }[];
} | null>(null);
const canDelete = (job: any) => !["running", "cancel_requested", "reconciling"].includes(job.state);
const selectionScope = computed(() =>
  JSON.stringify([query.value, state.value, tool.value, sort.value, page.value])
);
const loadedScope = ref("");
const selectionReady = computed(() => selectionScope.value === loadedScope.value);
const selectable = computed(() => (selectionReady.value ? items.value.filter(canDelete) : []));
const allSelected = computed(
  () => selectable.value.length > 0 && selectable.value.every((j) => selected.value.includes(j.id))
);
function toggleAll() {
  selected.value = allSelected.value ? [] : selectable.value.map((j) => j.id);
}
function askBatchDelete() {
  if (!selectionReady.value || !selected.value.length) return;
  batchDeleting.value = items.value.filter((j) => selected.value.includes(j.id));
  deleteError.value = "";
  batchResult.value = null;
}
async function removeBatch() {
  if (!batchDeleting.value?.length || busy.value) return;
  const snapshot = batchDeleting.value;
  busy.value = true;
  deleteError.value = "";
  try {
    const result = await api<{ deleted_ids: string[]; skipped: { id: string; message: string }[] }>(
      "/jobs/batch-delete",
      send("POST", { job_ids: snapshot.map((j) => j.id) })
    );
    batchResult.value = {
      deleted: result.deleted_ids.length,
      skipped: result.skipped.map((item) => ({
        ...item,
        title: snapshot.find((j) => j.id === item.id)?.title || item.id,
      })),
    };
    selected.value = [];
    batchDeleting.value = null;
    if (result.deleted_ids.includes(detail.value?.id)) detail.value = null;
    await load();
    emit("changed");
  } catch (e) {
    deleteError.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));
const runnable = computed(() => props.tools.filter((t) => t.mode === "job" && t.enabled));
const columns = computed(() =>
  [
    { id: "queued", name: "待执行", states: ["queued"] },
    { id: "running", name: "进行中 / 待核对", states: ["running", "cancel_requested", "reconciling"] },
    { id: "succeeded", name: "已完成", states: ["succeeded"] },
    { id: "failed", name: "失败 / 已取消", states: ["failed", "cancelled"] },
  ].map((col) => ({ ...col, items: items.value.filter((j) => col.states.includes(j.state)) }))
);
const toolName = (id: string) => props.tools.find((t) => t.id === id)?.name || id;
const when = (value: string) =>
  value
    ? new Date(value + "Z").toLocaleString("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "—";
let timer: ReturnType<typeof setInterval>,
  debounce: ReturnType<typeof setTimeout>,
  generation = 0,
  alive = true;

async function load() {
  if (!alive || document.hidden) return;
  const request = ++generation;
  const requestScope = selectionScope.value;
  loading.value = true;
  try {
    const args = new URLSearchParams({
      page: String(page.value),
      page_size: String(pageSize),
      q: query.value,
      state: state.value,
      tool_id: tool.value,
      sort: sort.value,
    });
    const data = await api<any>(`/jobs/query?${args}`);
    if (!alive || request !== generation) return;
    items.value = data.items;
    loadedScope.value = requestScope;
    selected.value = selected.value.filter((id) =>
      data.items.some((j: any) => j.id === id && canDelete(j))
    );
    total.value = data.total;
    error.value = "";
    if (page.value > pages.value) {
      page.value = pages.value;
      return;
    }
    if (detail.value) {
      const id = detail.value.id;
      try {
        const fresh = await api(`/jobs/${id}`);
        if (detail.value?.id === id) detail.value = fresh;
      } catch {
        /* Another tab may have removed this record. */
      }
    }
  } catch (e) {
    if (request === generation) error.value = (e as Error).message;
  } finally {
    if (request === generation) loading.value = false;
  }
}
watch([query, state, tool, sort], () => {
  selected.value = [];
  generation++;
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    if (page.value !== 1) page.value = 1;
    else void load();
  }, 250);
});
watch(page, () => {
  selected.value = [];
  void load();
});
watch(view, (value) => {
  try {
    localStorage.setItem(`tb:task-view:${props.userId}`, value);
  } catch {}
});
onMounted(() => {
  try {
    const saved = localStorage.getItem(`tb:task-view:${props.userId}`);
    if (modes.some((m) => m.id === saved)) view.value = saved!;
  } catch {}
  void load();
  timer = setInterval(load, 4000);
});
onUnmounted(() => {
  alive = false;
  generation++;
  clearInterval(timer);
  clearTimeout(debounce);
});
async function openDetail(job: any) {
  try {
    history.value = null;
    detail.value = await api(`/jobs/${job.id}`);
    const data = await api(`/jobs/${job.id}/events`);
    if (detail.value?.id === job.id) history.value = data;
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function openEdit(job: any) {
  try {
    const current = await api<any>(`/jobs/${job.id}`);
    title.value = current.title;
    params.value = JSON.stringify(current.params, null, 2);
    originalParams.value = params.value;
    editing.value = current;
    editError.value = "";
  } catch (e) {
    error.value = (e as Error).message;
  }
}
async function saveEdit() {
  busy.value = true;
  editError.value = "";
  try {
    const data: any = { title: title.value };
    if (editing.value.state === "queued" && params.value !== originalParams.value) {
      data.params = JSON.parse(params.value);
      if (!data.params || Array.isArray(data.params) || typeof data.params !== "object")
        throw new Error("参数必须是 JSON 对象");
    }
    await api(`/jobs/${editing.value.id}`, send("PATCH", data));
    editing.value = null;
    await load();
    emit("changed");
  } catch (e) {
    editError.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
function askDelete(job: any) {
  deleting.value = job;
  deleteError.value = "";
}
async function remove() {
  busy.value = true;
  deleteError.value = "";
  try {
    const id = deleting.value.id;
    await api(`/jobs/${id}`, { method: "DELETE" });
    deleting.value = null;
    if (detail.value?.id === id) detail.value = null;
    await load();
    emit("changed");
  } catch (e) {
    deleteError.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
async function action(job: any, verb: string) {
  busy.value = true;
  try {
    await api(`/jobs/${job.id}/${verb}`, {
      ...send("POST"),
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
    await load();
    emit("changed");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="task-center">
    <div class="page-heading">
      <div>
        <div class="section-kicker">YOUR TASK SPACE</div>
        <h1>每一步进展，清晰可见<span class="heading-dot">.</span></h1>
        <p>创建、管理与追踪任务，切换适合你的工作视角。</p>
      </div>
      <button class="primary" @click="showCreate = true"><Plus :size="17" />新建任务</button>
    </div>
    <div class="task-snapshot" aria-label="当前页任务概览">
      <div v-for="column in columns" :key="column.id" :data-state="column.id">
        <span><i></i>本页{{ column.name }}</span
        ><strong>{{ column.items.length }}<small>个任务</small></strong>
      </div>
    </div>
    <div class="task-control-panel">
      <div class="task-controls">
        <label class="task-search"
          ><Search :size="17" /><input
            v-model="query"
            aria-label="搜索任务"
            placeholder="搜索任务名称或完整 ID…"
            maxlength="200"
        /></label>
        <select v-model="state" aria-label="任务状态筛选">
          <option value="">全部状态</option>
          <option v-for="(name, key) in labels" :key="key" :value="key">{{ name }}</option>
        </select>
        <select v-model="tool" aria-label="任务工具筛选">
          <option value="">全部工具</option>
          <option v-for="t in tools.filter((t) => t.mode === 'job')" :key="t.id" :value="t.id">
            {{ t.name }}
          </option>
        </select>
        <select v-model="sort" aria-label="任务排序">
          <option value="newest">最新创建</option>
          <option value="oldest">最早创建</option>
        </select>
      </div>
      <div class="task-view-bar">
        <span
          >共 <b>{{ total }}</b> 个任务 <small>· 每页 {{ pageSize }} 条</small></span
        >
        <div class="task-view-switch" role="group" aria-label="任务视图">
          <button
            v-for="mode in modes"
            :key="mode.id"
            :class="{ active: view === mode.id }"
            :aria-label="mode.name"
            :aria-pressed="view === mode.id"
            @click="view = mode.id"
          >
            <component :is="mode.icon" :size="16" /><span>{{ mode.name.slice(0, 2) }}</span>
          </button>
        </div>
        <button class="icon-button" aria-label="刷新任务" @click="load">
          <RefreshCw :size="16" :class="{ spin: loading }" />
        </button>
      </div>
      <div class="task-batch-bar">
        <label class="task-select-all">
          <input
            type="checkbox"
            class="task-checkbox"
            aria-label="全选本页可删除任务"
            :checked="allSelected"
            :indeterminate="selected.length > 0 && !allSelected"
            :disabled="busy || !selectable.length"
            @change="toggleAll"
          />
          全选本页可删除任务
        </label>
        <span>已选 {{ selected.length }} 项</span>
        <button
          class="secondary danger"
          :disabled="busy || !selectionReady || !selected.length"
          @click="askBatchDelete"
        >
          <Trash2 :size="14" />批量删除
        </button>
        <button v-if="selected.length" class="text-link" :disabled="busy" @click="selected = []">
          清空选择
        </button>
        <small>切换页码或筛选会清空选择；运行中需先取消。</small>
      </div>
    </div>
    <div v-if="batchResult" class="task-batch-result" role="status">
      <strong
        >已删除 {{ batchResult.deleted }} 项，跳过
        {{ batchResult.skipped.length }} 项。已生成文件保留在文件中心。</strong
      >
      <details v-if="batchResult.skipped.length">
        <summary>查看跳过原因</summary>
        <ul>
          <li v-for="item in batchResult.skipped" :key="item.id">
            {{ item.title }}：{{ item.message }}
          </li>
        </ul>
      </details>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="!items.length" class="empty-state bordered">
      <Layers3 :size="40" />
      <h3>{{ query || state || tool ? "没有匹配的任务" : "还没有任务" }}</h3>
      <p>试试调整筛选条件，或创建一个新任务。</p>
      <button class="secondary" @click="showCreate = true">新建任务</button>
    </div>
    <div v-else-if="view === 'list'" class="task-table-wrap">
      <table class="task-table">
        <thead>
          <tr>
            <th class="task-select-cell">选择</th>
            <th>任务</th>
            <th>状态</th>
            <th>创建时间</th>
            <th>进度</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="job in items"
            :key="job.id"
            :class="{ 'task-selected': selected.includes(job.id) }"
            :data-state="job.state"
          >
            <td class="task-select-cell">
              <input
                v-model="selected"
                type="checkbox"
                class="task-checkbox"
                :value="job.id"
                :aria-label="`选择任务 ${job.title}`"
                :data-job-id="job.id"
                :disabled="busy || !selectionReady || !canDelete(job)"
              />
            </td>
            <td>
              <button class="task-title" @click="openDetail(job)">{{ job.title }}</button
              ><small>{{ toolName(job.tool_id) }} · {{ job.id.slice(0, 8) }}</small>
            </td>
            <td>
              <span class="status" :class="job.state">{{ labels[job.state] }}</span>
            </td>
            <td>{{ when(job.created_at) }}</td>
            <td>
              <div class="progress-track"><i :style="{ width: `${job.progress}%` }" /></div>
              <small>{{ job.progress }}%</small>
            </td>
            <td>
              <div class="task-row-actions">
                <button
                  v-if="job.result.asset_id"
                  class="text-link"
                  :aria-label="`预览 ${job.title}`"
                  @click="previewAsset = job.result.asset_id"
                >
                  <Play :size="14" />预览
                </button>
                <a
                  v-if="job.result.asset_id"
                  class="text-link"
                  :href="`/api/assets/${job.result.asset_id}/download`"
                  >下载</a
                >
                <button @click="openDetail(job)" :aria-label="`查看 ${job.title}`">详情</button
                ><button @click="openEdit(job)" :aria-label="`编辑 ${job.title}`">
                  <Pencil :size="13" />编辑</button
                ><button
                  :disabled="['running', 'cancel_requested', 'reconciling'].includes(job.state)"
                  @click="askDelete(job)"
                  :aria-label="`删除 ${job.title}`"
                >
                  <Trash2 :size="13" />删除
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="view === 'cards'" class="task-card-grid">
      <article
        v-for="job in items"
        :key="job.id"
        class="task-card"
        :class="{ 'task-selected': selected.includes(job.id) }"
        :data-state="job.state"
      >
        <div class="task-card-top">
          <input
            v-model="selected"
            type="checkbox"
            class="task-checkbox"
            :value="job.id"
            :aria-label="`选择任务 ${job.title}`"
            :data-job-id="job.id"
            :disabled="busy || !selectionReady || !canDelete(job)"
          />
          <span>{{ toolName(job.tool_id) }}</span
          ><span class="status" :class="job.state">{{ labels[job.state] }}</span>
        </div>
        <button class="task-title" @click="openDetail(job)">{{ job.title }}</button>
        <p class="task-message">{{ job.message }}</p>
        <div class="progress-track"><i :style="{ width: `${job.progress}%` }" /></div>
        <small>{{ when(job.created_at) }} · {{ job.progress }}%</small>
        <div class="task-card-actions">
          <button
            v-if="job.result.asset_id"
            class="text-link"
            :aria-label="`预览 ${job.title}`"
            @click="previewAsset = job.result.asset_id"
          >
            <Play :size="14" />预览
          </button>
          <button class="text-link" @click="openDetail(job)">查看详情</button
          ><button class="icon-button" :aria-label="`编辑 ${job.title}`" @click="openEdit(job)">
            <Pencil :size="15" /></button
          ><button
            class="icon-button"
            :aria-label="`删除 ${job.title}`"
            :disabled="['running', 'cancel_requested', 'reconciling'].includes(job.state)"
            @click="askDelete(job)"
          >
            <Trash2 :size="15" />
          </button>
        </div>
      </article>
    </div>
    <div v-else class="task-board">
      <section v-for="column in columns" :key="column.id" class="task-column">
        <h2>
          <i :class="column.id" />{{ column.name }}<span>{{ column.items.length }}</span>
        </h2>
        <article
          v-for="job in column.items"
          :key="job.id"
          class="task-card"
          :class="{ 'task-selected': selected.includes(job.id) }"
          :data-state="job.state"
        >
          <label class="task-board-select"
            ><input
              v-model="selected"
              type="checkbox"
              class="task-checkbox"
              :value="job.id"
              :aria-label="`选择任务 ${job.title}`"
              :data-job-id="job.id"
              :disabled="busy || !selectionReady || !canDelete(job)"
            />选择任务</label
          >
          <small>{{ toolName(job.tool_id) }}</small
          ><button class="task-title" @click="openDetail(job)">{{ job.title }}</button>
          <p class="task-message">{{ job.message }}</p>
          <div class="task-card-actions">
            <button
              v-if="job.result.asset_id"
              class="text-link"
              :aria-label="`预览 ${job.title}`"
              @click="previewAsset = job.result.asset_id"
            >
              <Play :size="14" />预览
            </button>
            <small>{{ when(job.created_at) }}</small
            ><button class="icon-button" :aria-label="`编辑 ${job.title}`" @click="openEdit(job)">
              <Pencil :size="14" /></button
            ><button
              class="icon-button"
              :aria-label="`删除 ${job.title}`"
              :disabled="['running', 'cancel_requested', 'reconciling'].includes(job.state)"
              @click="askDelete(job)"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </article>
        <p v-if="!column.items.length" class="task-column-empty">本页暂无任务</p>
      </section>
    </div>
    <p v-if="view === 'board'" class="field-hint">
      看板按当前页结果分组；任务状态由后台执行结果决定。
    </p>
    <div class="pagination">
      <button :disabled="page <= 1" @click="page--">上一页</button
      ><span>第 {{ page }} / {{ pages }} 页</span
      ><button :disabled="page >= pages" @click="page++">下一页</button>
    </div>

    <div v-if="showCreate" class="modal-backdrop" @click.self="showCreate = false">
      <section
        class="tool-modal task-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="新建任务"
        @keydown.esc="showCreate = false"
      >
        <div class="modal-heading">
          <div>
            <h2>新建任务</h2>
            <p>选择工具，填写参数后交给后台处理。</p>
          </div>
          <button class="icon-button" aria-label="关闭新建任务" @click="showCreate = false">
            <X />
          </button>
        </div>
        <div class="task-tool-picker">
          <button
            v-for="t in runnable"
            :key="t.id"
            @click="
              showCreate = false;
              emit('openTool', t);
            "
          >
            <strong>{{ t.name }}</strong
            ><span>{{ t.description }}</span>
          </button>
        </div>
      </section>
    </div>
    <AssetPreviewDialog v-if="previewAsset" :asset-id="previewAsset" @close="previewAsset = null" />
    <div v-if="detail" class="modal-backdrop" @click.self="detail = null">
      <section
        class="tool-modal task-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="任务详情"
        @keydown.esc="detail = null"
      >
        <div class="modal-heading">
          <div>
            <h2>{{ detail.title }}</h2>
            <p>{{ toolName(detail.tool_id) }} · {{ labels[detail.state] }}</p>
          </div>
          <button class="icon-button" aria-label="关闭任务详情" @click="detail = null">
            <X />
          </button>
        </div>
        <p class="task-detail-message" :class="{ error: detail.state === 'failed' }">
          {{ detail.message }}
        </p>
        <dl class="task-facts">
          <dt>任务 ID</dt>
          <dd>{{ detail.id }}</dd>
          <dt>创建</dt>
          <dd>{{ when(detail.created_at) }}</dd>
          <dt>开始</dt>
          <dd>{{ when(detail.started_at) }}</dd>
          <dt>结束</dt>
          <dd>{{ when(detail.finished_at) }}</dd>
          <dt>工具版本</dt>
          <dd>{{ detail.plugin_id ? `${detail.plugin_id} / ${detail.plugin_version}` : '升级前任务' }}</dd>
          <template v-if="detail.parent_job_id"><dt>关联原任务</dt><dd>{{ detail.parent_job_id }}</dd></template>
        </dl>
        <p v-if="detail.state === 'reconciling'" class="field-hint">外部服务结果尚未确认。请根据任务记录核对配音服务结果，核对前不能重试或删除。</p>
        <details v-if="history" class="task-input-details">
          <summary>执行记录 · {{ history.events.length }} 条</summary>
          <p v-if="!history.events.length" class="field-hint">升级前的任务未记录执行事件。</p>
          <dl v-for="event in history.events" :key="event.id" class="task-facts">
            <dt>{{ when(event.created_at) }}</dt>
            <dd>{{ eventNames[event.event_type] || event.event_type }}<template v-if="event.payload.error_code"> · {{ event.payload.error_code }}</template></dd>
          </dl>
        </details>
        <details class="task-input-details">
          <summary>查看输入参数</summary>
          <pre>{{ JSON.stringify(detail.params, null, 2) }}</pre>
        </details>
        <MediaPreview v-if="detail.result.asset_id" :asset-id="detail.result.asset_id" />
        <div class="task-dialog-actions">
          <button class="secondary" @click="openEdit(detail)">编辑任务</button
          ><button
            v-if="['queued', 'running'].includes(detail.state)"
            class="secondary"
            :disabled="busy"
            @click="action(detail, 'cancel')"
          >
            取消任务</button
          ><button
            v-if="['failed', 'cancelled'].includes(detail.state)"
            class="primary"
            :disabled="busy"
            @click="action(detail, 'retry')"
          >
            重试任务</button
          ><button
            class="secondary danger"
            :disabled="['running', 'cancel_requested', 'reconciling'].includes(detail.state)"
            @click="askDelete(detail)"
          >
            删除任务
          </button>
        </div>
      </section>
    </div>
    <div
      v-if="editing"
      class="modal-backdrop task-edit-overlay"
      @click.self="!busy && (editing = null)"
    >
      <form
        class="tool-modal task-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="编辑任务"
        @submit.prevent="saveEdit"
      >
        <div class="modal-heading">
          <h2>编辑任务</h2>
          <button
            type="button"
            class="icon-button"
            aria-label="关闭编辑任务"
            :disabled="busy"
            @click="editing = null"
          >
            <X />
          </button>
        </div>
        <label
          >任务名称<input v-model="title" required maxlength="200" aria-label="任务名称" /></label
        ><label v-if="editing.state === 'queued'"
          >输入参数（JSON）<textarea
            v-model="params"
            rows="9"
            spellcheck="false"
            aria-label="任务输入参数"
          />
        </label>
        <p class="field-hint">修改排队任务的参数会取消原任务，并创建关联的新任务；历史输入会保留。</p>
        <p v-if="editError" class="error" role="alert">{{ editError }}</p>
        <button class="primary" :disabled="busy">{{ busy ? "保存中…" : "保存修改" }}</button>
      </form>
    </div>
    <div
      v-if="batchDeleting"
      class="modal-backdrop task-edit-overlay"
      @click.self="!busy && (batchDeleting = null)"
    >
      <section
        class="tool-modal task-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label="批量删除任务确认"
      >
        <h2>删除选中的 {{ batchDeleting.length }} 条任务记录？</h2>
        <ul class="task-batch-preview">
          <li v-for="job in batchDeleting" :key="job.id">
            {{ job.title }} <small>{{ job.id.slice(0, 8) }}</small>
          </li>
        </ul>
        <p class="field-hint">
          删除后无法恢复记录，已生成文件仍保留。等待中的任务将停止派发；已经开始运行的任务会跳过并说明原因。
        </p>
        <p v-if="deleteError" class="error" role="alert">{{ deleteError }}</p>
        <div class="task-dialog-actions">
          <button class="secondary" :disabled="busy" @click="batchDeleting = null">保留任务</button>
          <button class="primary" :disabled="busy" @click="removeBatch">
            {{ busy ? "删除中…" : "确认批量删除" }}
          </button>
        </div>
      </section>
    </div>
    <div
      v-if="deleting"
      class="modal-backdrop task-edit-overlay"
      @click.self="!busy && (deleting = null)"
    >
      <section
        class="tool-modal task-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label="删除任务确认"
      >
        <h2>删除这条任务记录？</h2>
        <p class="task-delete-title">{{ deleting.title }}</p>
        <p class="field-hint">
          删除后无法恢复记录，已生成文件仍保留在文件中心。等待中的任务将停止派发。
        </p>
        <p v-if="deleteError" class="error" role="alert">{{ deleteError }}</p>
        <div class="task-dialog-actions">
          <button class="secondary" :disabled="busy" @click="deleting = null">保留任务</button
          ><button class="primary" :disabled="busy" @click="remove">
            {{ busy ? "删除中…" : "确认删除" }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>
