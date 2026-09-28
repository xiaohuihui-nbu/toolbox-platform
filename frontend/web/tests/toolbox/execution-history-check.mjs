import { chromium, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve('../..'), base = 'http://127.0.0.1:18990';
const password = (await readFile(resolve(root, '.env'), 'utf8')).match(/^TB_ADMIN_PASSWORD=(.+)$/m)[1].trim();
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({ viewport: { width: 1400, height: 1000 } });
const page = await context.newPage(), errors = [];
page.on('pageerror', error => errors.push(error.message));
// UI-only fixture; durable history and owner checks have separate real DB tests.
const job = { id: 'qa-history-fixture', title: '待核对配音验收', tool_id: 'tts.natural',
  state: 'reconciling', stage: 'reconciling', progress: 35, message: '外部执行结果待核对',
  params: { text: '样例' }, result: {}, plugin_id: 'tts', plugin_version: '1.0.0',
  created_at: '2026-09-24T07:00:00', started_at: '2026-09-24T07:00:01', finished_at: null };
try {
  expect((await context.request.post(base + '/api/auth/login', { data: { username: 'admin', password } })).ok()).toBeTruthy();
  await page.route('**/api/v1/toolbox/jobs/query?**', route => route.fulfill({ json: { items: [job], total: 1, page: 1, page_size: 24 } }));
  await page.route('**/api/v1/toolbox/jobs/qa-history-fixture', route => route.fulfill({ json: job }));
  await page.route('**/api/v1/toolbox/jobs/qa-history-fixture/events', route => route.fulfill({ json: {
    attempts: [{ id: 'attempt-1', attempt_no: 1, state: 'reconciling' }],
    events: [{ id: 1, event_type: 'reconciling', created_at: job.created_at, payload: { error_code: 'SUBMISSION_UNCERTAIN' } }],
  } }));
  await page.goto(base + '/#/jobs');
  for (const mode of ['列表视图', '卡片视图', '看板视图']) {
    await page.getByRole('button', { name: mode, exact: true }).click();
    await expect(page.getByRole('button', { name: job.title, exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: `删除 ${job.title}`, exact: true })).toBeDisabled();
  }
  console.log('PASS Reconciliation remains visible in every task view and cannot be batch deleted');
  await page.getByRole('button', { name: job.title, exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '任务详情', exact: true });
  await expect(dialog.getByText('tts / 1.0.0')).toBeVisible();
  await dialog.locator('summary').filter({ hasText: '执行记录' }).click();
  await expect(dialog.getByText('等待核对 · SUBMISSION_UNCERTAIN')).toBeVisible();
  await expect(dialog.getByRole('button', { name: '删除任务', exact: true })).toBeDisabled();
  await expect(dialog.getByRole('button', { name: '重试任务', exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
  console.log('PASS Task detail shows version and durable event fields without offering unsafe retry');
} finally { await browser.close(); }
