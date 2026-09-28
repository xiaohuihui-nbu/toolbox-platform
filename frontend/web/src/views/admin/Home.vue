<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
const router = useRouter();
const runtime = ref<any>(null), error = ref('');
onMounted(async () => {
  try {
    const r = await fetch('/api/v1/toolbox/admin/runtime');
    if (!r.ok) throw new Error('执行器状态暂不可用');
    runtime.value = await r.json();
  } catch (e) { error.value = (e as Error).message; }
});
const entries = [ ['用户管理', '/system/user', '管理团队账号和角色'], ['角色管理', '/system/role', '配置菜单与工具权限'],
  ['菜单管理', '/system/menu', '管理页面与按钮权限'], ['操作日志', '/system/log', '查询登录与操作记录'] ];
</script>
<template>
  <section aria-label="FastapiAdmin 管理概览">
    <ElCard><h1>FastapiAdmin 管理后台</h1><p style="margin:16px 0">管理团队账号、角色权限、组织结构与操作日志。</p>
      <ElButton type="primary" @click="router.push('/system/user')">管理用户</ElButton>
      <a href="/#/home" style="margin-left:20px;color:var(--el-color-primary)">返回工具箱工作台</a>
    </ElCard>
    <ElRow :gutter="20" style="margin-top:20px"><ElCol v-for="[title,path,description] in entries" :key="path" :xs="24" :sm="12" :lg="6" style="margin-bottom:20px">
      <ElCard><h2 style="margin-bottom:12px">{{ title }}</h2><p style="margin-bottom:16px">{{ description }}</p><ElButton @click="router.push(path)">进入管理</ElButton></ElCard>
    </ElCol></ElRow>
    <ElCard><template #header>工具执行器</template><p v-if="error">{{ error }}</p><p v-else-if="!runtime">正在读取状态…</p>
      <ElDescriptions v-else :column="3" border><ElDescriptionsItem v-for="p in runtime.profiles" :key="p.name" :label="({download:'视频下载',media_cpu:'媒体处理',provider_io:'配音服务'})[p.name] || p.name"><ElTag :type="p.ready?'success':'warning'">{{ p.ready?'已就绪':'未就绪' }}</ElTag></ElDescriptionsItem></ElDescriptions>
    </ElCard>
  </section>
</template>
