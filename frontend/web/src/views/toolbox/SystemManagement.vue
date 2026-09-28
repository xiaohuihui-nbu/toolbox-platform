<script setup lang="ts">
import { ref, onMounted } from "vue";
import {
  ElDialog, ElTabs, ElTabPane, ElTable, ElTableColumn, ElButton,
  ElSelect, ElOption, ElCheckboxGroup, ElCheckbox, ElInput, ElSwitch,
} from "element-plus";
import "element-plus/dist/index.css";
import { systemApi } from "../../api/toolbox/system";

const visible = defineModel<boolean>({ required: true });
const tab = ref("users"), users = ref<any[]>([]), roles = ref<any[]>([]), menus = ref<any[]>([]), logs = ref<any[]>([]);
const error = ref(""), message = ref(""), busy = ref(false), roleId = ref<number>();
const userPage = ref(1), userTotal = ref(0), logPage = ref(1), logTotal = ref(0);
const selectedMenus = ref<number[]>([]), roleName = ref(""), roleCode = ref("");
const flatten = (items: any[]): any[] => items.flatMap(item => [item, ...flatten(item.children || [])]);
async function action(work: () => Promise<void>) {
  busy.value = true; error.value = ""; message.value = "";
  try { await work(); } catch (e) { error.value = e instanceof Error ? e.message : "操作失败"; }
  finally { busy.value = false; }
}
async function loadUsers() {
  const data = await systemApi(`/user/list?page_no=${userPage.value}&page_size=20`);
  users.value = data.items; userTotal.value = data.total;
}
async function loadRoles() {
  roles.value = await systemApi("/role/options");
  menus.value = flatten(await systemApi("/menu/tree")).filter(item => item.type === 3 && item.permission?.startsWith("toolbox:"));
}
async function loadRole() {
  if (!roleId.value) return;
  const role = await systemApi(`/role/detail/${roleId.value}`);
  selectedMenus.value = role.menus.map((menu: any) => menu.id);
}
async function saveUser(row: any) {
  await action(async () => {
    await systemApi(`/user/update/${row.id}`, "PUT", { name: row.name, status: row.status, role_ids: row.role_ids, position_ids: row.position_ids || [] });
    await loadUsers(); message.value = "账号已更新；工具权限立即生效。";
  });
}
async function addRole() {
  await action(async () => {
    const role = await systemApi("/role/create", "POST", { name: roleName.value, code: roleCode.value, status: 0, data_scope: 1 });
    roleId.value = role.id; roleName.value = ""; roleCode.value = "";
    await loadRoles(); await loadRole(); message.value = "角色已创建，请选择允许使用的工具。";
  });
}
async function savePermissions() {
  await action(async () => {
    const role = await systemApi(`/role/detail/${roleId.value}`);
    await systemApi("/role/permission", "PUT", { role_ids: [roleId.value], menu_ids: selectedMenus.value, data_scope: role.data_scope, dept_ids: (role.depts || []).map((dept: any) => dept.id) });
    message.value = "工具授权已保存。现有账号无需重新登录。";
  });
}
async function loadLogs() {
  const data = await systemApi(`/log/operation/list?page_no=${logPage.value}&page_size=20`);
  logs.value = data.items; logTotal.value = data.total;
}
onMounted(() => action(async () => { await loadUsers(); await loadRoles(); await loadLogs(); }));
</script>

<template>
  <ElDialog v-model="visible" title="用户、角色与审计管理" width="min(1060px, 94vw)" class="toolbox-system-admin" destroy-on-close>
    <p class="system-caption">统一管理团队账号和工具使用权限。任务与文件继续按所属账号隔离。</p>
    <p v-if="error" role="alert" class="system-error">{{ error }}</p>
    <p v-if="message" role="status" class="system-success">{{ message }}</p>
    <ElTabs v-model="tab">
      <ElTabPane label="用户管理" name="users">
        <ElTable :data="users" max-height="440" empty-text="暂无用户">
          <ElTableColumn prop="username" label="账号" width="140" />
          <ElTableColumn label="名称" min-width="130"><template #default="{ row }"><ElInput v-model="row.name" :disabled="row.is_superuser" maxlength="32" :aria-label="`${row.username}名称`" /></template></ElTableColumn>
          <ElTableColumn label="角色" min-width="220"><template #default="{ row }">
            <span v-if="row.is_superuser">超级管理员</span>
            <ElSelect v-else v-model="row.role_ids" multiple :aria-label="`${row.username}角色`"><ElOption v-for="role in roles" :key="role.value" :label="role.label" :value="role.value" /></ElSelect>
          </template></ElTableColumn>
          <ElTableColumn label="启用" width="90"><template #default="{ row }"><ElSwitch v-model="row.status" :active-value="0" :inactive-value="1" :disabled="row.is_superuser" :aria-label="`${row.username}启用状态`" /></template></ElTableColumn>
          <ElTableColumn label="操作" width="95"><template #default="{ row }"><ElButton :disabled="row.is_superuser || busy" @click="saveUser(row)">保存</ElButton></template></ElTableColumn>
        </ElTable>
        <div class="system-pagination"><span>共 {{ userTotal }} 个账号 · 第 {{ userPage }} 页</span><ElButton :disabled="userPage === 1 || busy" @click="userPage--; action(loadUsers)">上一页</ElButton><ElButton :disabled="userPage * 20 >= userTotal || busy" @click="userPage++; action(loadUsers)">下一页</ElButton></div>
      </ElTabPane>
      <ElTabPane label="角色与工具授权" name="roles">
        <form class="system-role-form" @submit.prevent="addRole">
          <ElInput v-model="roleName" placeholder="新角色名称" aria-label="新角色名称" maxlength="64" />
          <ElInput v-model="roleCode" placeholder="角色编码，例如 video_editor" aria-label="新角色编码" maxlength="64" />
          <ElButton native-type="submit" :disabled="busy || !roleName || roleCode.length < 2">创建角色</ElButton>
        </form>
        <ElSelect v-model="roleId" :disabled="busy" placeholder="选择要授权的角色" aria-label="选择授权角色" @change="action(loadRole)"><ElOption v-for="role in roles" :key="role.value" :label="role.label" :value="role.value" /></ElSelect>
        <ElCheckboxGroup v-if="roleId" v-model="selectedMenus" :disabled="busy" class="system-permissions"><ElCheckbox v-for="menu in menus" :key="menu.id" :value="menu.id">{{ menu.name }}</ElCheckbox></ElCheckboxGroup>
        <ElButton type="primary" :disabled="busy || !roleId" @click="savePermissions">保存工具授权</ElButton>
      </ElTabPane>
      <ElTabPane label="操作审计" name="logs">
        <ElTable :data="logs" max-height="460" empty-text="暂无记录">
          <ElTableColumn prop="created_time" label="时间" width="175" />
          <ElTableColumn prop="username" label="操作者" width="130" />
          <ElTableColumn prop="request_method" label="方法" width="85" />
          <ElTableColumn prop="request_path" label="操作路径" min-width="240" />
          <ElTableColumn prop="response_code" label="状态" width="80" />
        </ElTable>
        <div class="system-pagination"><span>共 {{ logTotal }} 条 · 第 {{ logPage }} 页</span><ElButton :disabled="logPage === 1 || busy" @click="logPage--; action(loadLogs)">上一页</ElButton><ElButton :disabled="logPage * 20 >= logTotal || busy" @click="logPage++; action(loadLogs)">下一页</ElButton><ElButton :disabled="busy" @click="action(loadLogs)">刷新记录</ElButton></div>
      </ElTabPane>
    </ElTabs>
  </ElDialog>
</template>

<style>
.toolbox-system-admin { --el-color-primary: #687aff; border-radius: 18px; }
html[data-theme="dark"] .toolbox-system-admin {
  --el-bg-color: #151b2a; --el-bg-color-overlay: #20283a; --el-fill-color-blank: #151b2a;
  --el-fill-color-light: #222c41; --el-text-color-primary: #e9eef9; --el-text-color-regular: #c2cde0;
  --el-text-color-secondary: #95a5c2; --el-border-color: #35405a; --el-border-color-light: #2c354b;
  --el-border-color-lighter: #2c354b; background: #151b2a; color: #e9eef9;
}
.system-caption { margin: 0 0 18px; opacity: .8; }
.system-error { color: #ef6464; margin-bottom: 12px; }
.system-success { color: #37ad86; margin-bottom: 12px; }
.system-role-form { display: flex; gap: 12px; margin-bottom: 24px; }
.system-permissions { display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); margin: 22px 0; }
.system-pagination { display:flex; align-items:center; gap:10px; margin-top:18px; flex-wrap:wrap; }
.system-pagination span { margin-right:auto; }
@media(max-width:600px) { .system-role-form { flex-direction:column; } }
</style>
