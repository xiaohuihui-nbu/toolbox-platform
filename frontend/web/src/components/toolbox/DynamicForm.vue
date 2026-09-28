<script setup lang="ts">
import { CloudUpload, ShieldCheck, LoaderCircle, Play } from "lucide-vue-next";
defineProps<{
  selected: any;
  form: Record<string, any>;
  schemaFields: [string, any][];
  voices: { id: string; name: string; description: string }[];
  assets: any[];
  ttsState: string;
  busy: boolean;
  fileBusy: boolean;
  formError: string;
}>();
const emit = defineEmits<{ submit: []; refreshVoices: []; upload: [event: Event] }>();
</script>
<template>
  <form
    @submit.prevent="emit('submit')"
    class="tool-form"
    :class="{ 'natural-form': selected.id === 'tts.natural' }"
  >
    <div v-if="selected.id === 'tts.natural'" class="tts-provider-status">
      <span :class="{ ready: ttsState === 'ready' }">{{
        ttsState === "ready"
          ? "GPT-SoVITS · CPU 已就绪"
          : ttsState === "loading"
            ? "正在检查配音引擎…"
            : "配音引擎尚未就绪"
      }}</span
      ><button type="button" class="text-link" @click="emit('refreshVoices')">刷新状态</button>
    </div>
    <label v-for="[key, field] in schemaFields" :key="key"
      >{{ field.title
      }}<template v-if="key === 'asset_id'"
        ><select v-model="form[key]" required>
          <option value="" disabled>选择文件中心的音视频文件</option>
          <option v-for="asset in assets" :key="asset.id" :value="asset.id">
            {{ asset.name }}
          </option></select
        ><span class="field-hint">选择已有文件，或上传新文件（最大 100 MB）。</span
        ><label class="secondary inline-upload"
          ><CloudUpload :size="16" />{{ fileBusy ? "正在上传…" : "上传文件"
          }}<input
            type="file"
            accept="audio/*,video/*"
            :disabled="fileBusy"
            @change="emit('upload', $event)" /></label></template
      ><template v-else-if="key === 'voice_id'"
        ><select v-model="form[key]" required>
          <option v-for="voice in voices" :key="voice.id" :value="voice.id">
            {{ voice.name }} · {{ voice.description }}
          </option></select
        ><span class="field-hint">参考音试听（与最终文案的语气可能不同）</span
        ><audio
          v-if="voices.length"
          :key="form[key]"
          class="voice-sample"
          controls
          preload="none"
          :src="`/api/tts/voices/${form[key]}/preview`"
          aria-label="音色参考试听"
        ></audio></template
      ><select v-else-if="field.enum" v-model="form[key]">
        <option v-for="option in field.enum" :key="option" :value="option">
          {{ String(option).toUpperCase() }}
        </option></select
      ><select v-else-if="key === 'language'" v-model="form[key]">
        <option value="cmn">中文 · 基础离线音色</option>
        <option value="en-us">英语 · 基础离线音色</option></select
      ><input
        v-else-if="['integer', 'number'].includes(field.type)"
        type="number"
        v-model.number="form[key]"
        :min="field.minimum"
        :max="field.maximum"
        :step="field.type === 'integer' ? 1 : 0.05"
        required /><textarea
        v-else-if="key === 'text'"
        v-model="form[key]"
        :maxlength="field.maxLength"
        required
        rows="6"
        placeholder="写下你想处理的内容…"
      ></textarea
      ><input
        v-else
        v-model="form[key]"
        :type="field.format === 'uri' ? 'url' : 'text'"
        required
        placeholder="https://…"
    /></label>
    <p v-if="selected.id === 'audio.extract'" class="field-hint">
      首版每次最多提取前 10 分钟，输出 MP3。
    </p>
    <p v-if="formError" class="error" role="alert">{{ formError }}</p>
    <div class="modal-footer">
      <span><ShieldCheck :size="14" />结果仅在你的空间可见</span
      ><button
        class="primary"
        :disabled="busy || fileBusy || (selected.id === 'tts.natural' && ttsState !== 'ready')"
      >
        <LoaderCircle v-if="busy" class="spin" :size="17" /><Play v-else :size="16" />{{
          busy ? "正在提交…" : "开始处理"
        }}
      </button>
    </div>
  </form>
</template>
