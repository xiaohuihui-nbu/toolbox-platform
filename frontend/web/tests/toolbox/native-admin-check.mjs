import { chromium, expect } from '@playwright/test';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve('../..'), base = process.env.TB_TEST_BASE || 'http://127.0.0.1:18990';
const password = (await readFile(resolve(root, '.env'), 'utf8')).match(/^TB_ADMIN_PASSWORD=(.+)$/m)[1].trim();
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(), errors = [], checks = [];
let roleId;
const pass = text => { checks.push(text); console.log('PASS ' + text); };
page.on('pageerror', e => errors.push(e.message));
page.on('response', r => {
  if (r.status() >= 400 && !(r.status() === 401 && r.url().endsWith('/toolbox/me'))) errors.push(`${r.status()} ${r.url()}`);
});
try {
  await page.goto(base + '/admin/');
  await page.getByPlaceholder('请输入账号', { exact: true }).fill('admin');
  await page.getByPlaceholder('请输入密码', { exact: true }).fill(password);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'FastapiAdmin 管理后台', exact: true })).toBeVisible();
  expect((await context.cookies()).find(c => c.name === 'fa_session')?.httpOnly).toBe(true);
  expect((await context.request.get(base + '/api/v1/toolbox/me')).ok()).toBe(true);
  pass('Native login and workbench share the HttpOnly session');
  for (const route of ['user', 'role', 'menu', 'dept', 'position', 'dict', 'log']) {
    await page.goto(base + '/admin/#/system/' + route);
    await expect(page.locator('.el-table').first()).toBeVisible();
    await expect(page.locator('.el-loading-mask:visible')).toHaveCount(0);
    expect(await page.locator('body').innerText()).not.toContain('[路由警告]');
    pass('Native page renders: ' + route);
  }
  await page.goto(base + '/admin/#/system/role');
  await page.getByRole('button', { name: '新增', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '新增角色' });
  const code = 'qa' + Date.now().toString(36), name = '后台验收' + code;
  await dialog.getByPlaceholder('请输入角色名称').fill(name);
  await dialog.getByPlaceholder('字母开头，2-16位字母/数字/下划线').fill(code);
  const created = page.waitForResponse(r => r.url().endsWith('/system/role/create') && r.request().method() === 'POST');
  await dialog.getByRole('button', { name: '确定', exact: true }).click();
  const response = await created;
  expect(response.ok()).toBe(true);
  roleId = (await response.json()).data.id;
  expect(roleId).toBeTruthy();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  const detail = await context.request.get(base + `/api/v1/system/role/detail/${roleId}`);
  expect((await detail.json()).data.code).toBe(code);
  pass('Native role form persists through FastapiAdmin service and database');
  await page.reload();
  await expect(page.locator('.el-table').first()).toBeVisible();
  await page.screenshot({ path: resolve(root, 'artifacts/native-admin.png'), fullPage: true });
  expect(errors).toEqual([]);
  pass('Direct admin reload has no missing APIs, assets or JavaScript errors');
  await context.request.delete(base + '/api/v1/system/role/delete', { data: [roleId] }); roleId = undefined;
  await context.request.post(base + '/api/v1/toolbox/auth/logout');
  await page.reload();
  await expect(page.getByRole('button', { name: '登录', exact: true })).toBeVisible();
  expect((await context.request.get(base + '/api/v1/toolbox/me')).status()).toBe(401);
  pass('Logout revokes access for both applications');
  await writeFile(resolve(root, 'artifacts/native-admin-check.json'), JSON.stringify({ base, checks, errors }, null, 2));
} finally {
  if (roleId) await context.request.delete(base + '/api/v1/system/role/delete', { data: [roleId] });
  await context.request.post(base + '/api/v1/toolbox/auth/logout');
  await browser.close();
}
