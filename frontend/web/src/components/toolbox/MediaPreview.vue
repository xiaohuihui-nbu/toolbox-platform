<script setup lang="ts">
import { ref, watch } from "vue";
import { AudioLines, Download, LoaderCircle } from "lucide-vue-next";
import { api } from "../../api/toolbox";
const props = defineProps<{ assetId: string }>();
const asset = ref<any>(null),
  error = ref(""),
  loading = ref(true),
  ready = ref(false);
let generation = 0;
watch(
  () => props.assetId,
  async (id) => {
    const current = ++generation;
    asset.value = null;
    error.value = "";
    loading.value = true;
    ready.value = false;
    try {
      const data = await api(`/assets/${id}`);
      if (current === generation) asset.value = data;
    } catch (e) {
      if (current === generation) error.value = (e as Error).message;
    } finally {
      if (current === generation) loading.value = false;
    }
  },
  { immediate: true }
);
</script>
<template>
  <div class="media-panel">
    <p v-if="loading" class="media-hint"><LoaderCircle class="spin" :size="16" />正在加载文件…</p>
    <template v-if="asset">
      <div class="media-caption">
        <strong>{{ asset.name }}</strong
        ><span>{{ (asset.size / 1024 / 1024).toFixed(2) }} MB</span>
      </div>
      <div v-if="asset.preview_kind === 'video'" class="video-stage">
        <video
          :key="assetId"
          :src="`/api/assets/${assetId}/preview`"
          controls
          playsinline
          preload="metadata"
          aria-label="视频预览"
          @loadedmetadata="ready = true"
          @error="error = '浏览器无法播放此编码，请下载后使用本地播放器打开。'"
        ></video>
      </div>
      <div v-else-if="asset.preview_kind === 'audio'" class="audio-stage">
        <div class="audio-preview-art">
          <AudioLines :size="38" /><span>声音已就绪，按下播放试听</span>
        </div>
        <audio
          :key="assetId"
          :src="`/api/assets/${assetId}/preview`"
          controls
          preload="metadata"
          aria-label="语音试听"
          @loadedmetadata="ready = true"
          @error="error = '音频加载失败或编码不受支持，请下载后打开。'"
        ></audio>
      </div>
      <p v-else class="media-hint">此类型暂不支持在线预览，可下载后打开。</p>
      <div class="media-actions">
        <small>{{
          asset.preview_kind
            ? ready
              ? "可播放、调节音量和拖动进度"
              : "播放器正在读取媒体信息"
            : "文件仅本人可访问"
        }}</small
        ><a class="secondary" :href="`/api/assets/${assetId}/download`"
          ><Download :size="15" />下载原文件</a
        >
      </div>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>
