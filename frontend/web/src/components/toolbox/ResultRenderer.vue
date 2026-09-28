<script setup lang="ts">
import { Check, ArrowRight } from "lucide-vue-next";
import MediaPreview from "./MediaPreview.vue";
defineProps<{ job: any; stateLabels: Record<string, string> }>();
const emit = defineEmits<{ openJobs: [] }>();
</script>
<template>
  <div class="submit-success">
    <span><Check :size="32" /></span>
    <h3>
      {{ job?.state === "succeeded" ? "处理完成，可以预览了" : job?.state === "reconciling" ? "外部结果待核对" : "已加入任务队列" }}
    </h3>
    <p>
      {{ job?.message || "工具正在接手这件事。你可以继续其他工作。" }}
    </p>
    <MediaPreview v-if="job?.result.asset_id" :asset-id="job.result.asset_id" />
    <p v-else-if="job && ['failed', 'cancelled', 'reconciling'].includes(job.state)" class="error">
      {{ stateLabels[job.state] }}，可到任务中心查看详情。
    </p>
    <button class="primary" @click="emit('openJobs')">查看任务进度<ArrowRight :size="17" /></button>
  </div>
</template>
