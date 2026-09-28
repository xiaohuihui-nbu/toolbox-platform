<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { X } from "lucide-vue-next";
import MediaPreview from "./MediaPreview.vue";

defineProps<{ assetId: string }>();
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLDialogElement>();
onMounted(() => dialog.value?.showModal());
onUnmounted(() => dialog.value?.close());
</script>

<template>
  <dialog
    ref="dialog"
    class="tool-modal preview-modal asset-preview-dialog"
    aria-label="播放预览"
    @cancel.prevent="emit('close')"
    @keydown.stop
  >
    <div class="modal-heading">
      <div>
        <h2>播放预览</h2>
        <p>已保存的文件 · 支持播放与拖动进度</p>
      </div>
      <button class="icon-button" aria-label="关闭播放预览" autofocus @click="emit('close')">
        <X :size="20" />
      </button>
    </div>
    <MediaPreview :asset-id="assetId" />
  </dialog>
</template>

<style scoped>
.asset-preview-dialog {
  margin: auto;
  width: min(800px, calc(100vw - 32px));
  max-height: calc(100dvh - 32px);
  color: var(--text);
  overflow: auto;
}
.asset-preview-dialog::backdrop {
  background: #04091999;
  backdrop-filter: blur(5px);
}
</style>
