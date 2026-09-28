import { chromium, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";

const root = resolve("../.."),
  base = "http://127.0.0.1:18990";
const password = (await readFile(resolve(root, ".env"), "utf8"))
  .match(/^TB_ADMIN_PASSWORD=(.+)$/m)[1]
  .trim();
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1050 },
  locale: "zh-CN",
});
const page = await context.newPage(),
  jobs = [],
  checks = [],
  errors = [];
const prefix = "批删验收 " + randomUUID().slice(0, 8);
let originalPreferences;
const pass = (name) => {
  checks.push(name);
  console.log("PASS " + name);
};
page.on("pageerror", (e) => errors.push(e.message));
const api = async (path, method = "GET", data) => {
  const res = await context.request.fetch(`${base}/api${path}`, {
    method,
    data,
    headers: { "Idempotency-Key": randomUUID() },
  });
  expect(res.ok()).toBeTruthy();
  return res.json();
};
try {
  await api("/auth/login", "POST", { username: "admin", password });
  originalPreferences = (await api("/me")).preferences;
  for (let i = 0; i < 3; i++) {
    const job = await api("/jobs", "POST", {
      tool_id: "text.export",
      params: { text: `${prefix} 样例 ${i}` },
    });
    jobs.push(job);
    await expect
      .poll(async () => (await api(`/jobs/${job.id}`)).state, { timeout: 40000 })
      .toBe("succeeded");
    await api(`/jobs/${job.id}`, "PATCH", { title: `${prefix} ${i + 1}` });
  }
  await page.goto(base + "/#jobs");
  await page.getByRole("button", { name: "列表视图", exact: true }).click();
  await page.getByLabel("搜索任务", { exact: true }).fill(prefix);
  await expect(page.locator(".task-table tbody tr")).toHaveCount(3);
  const all = page.getByRole("checkbox", { name: "全选本页可删除任务", exact: true });
  const select = (job) => page.locator(`input[data-job-id="${job.id}"]`);
  const batch = page.getByRole("button", { name: "批量删除", exact: true });
  await expect(batch).toBeDisabled();
  await select(jobs[0]).check();
  await expect(all).toHaveJSProperty("indeterminate", true);
  await expect(page.getByText("已选 1 项", { exact: true })).toBeVisible();
  pass("Individual selection and select-all indeterminate state");
  for (const mode of ["卡片视图", "看板视图", "列表视图"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    await expect(select(jobs[0])).toBeChecked();
    pass(mode + " preserves selection");
  }
  await all.check();
  await expect(page.getByText("已选 3 项", { exact: true })).toBeVisible();
  await batch.click();
  const dialog = page.getByRole("alertdialog", { name: "批量删除任务确认" });
  await expect(dialog.locator(".task-batch-preview li")).toHaveCount(3);
  await dialog.getByRole("button", { name: "保留任务" }).click();
  expect((await api(`/jobs/query?q=${encodeURIComponent(prefix)}`)).total).toBe(3);
  pass("Confirmation lists exact scope; cancel preserves records");
  let releaseFilter, filterStarted;
  const filterGate = new Promise((resolve) => {
    releaseFilter = resolve;
  });
  const filterRequest = new Promise((resolve) => {
    filterStarted = resolve;
  });
  await page.route(
    "**/api/jobs/query?**",
    async (route) => {
      filterStarted();
      await filterGate;
      await route.continue();
    },
    { times: 1 }
  );
  await page.getByLabel("任务状态筛选").selectOption("failed");
  await filterRequest;
  try {
    await expect(all).toBeDisabled();
    await expect(select(jobs[0])).toBeDisabled();
    await expect(batch).toBeDisabled();
    pass("Pending filter cannot select or delete stale results");
  } finally {
    releaseFilter();
  }
  await expect(page.getByText("已选 0 项", { exact: true })).toBeVisible();
  await expect(page.getByText("没有匹配的任务", { exact: true })).toBeVisible();
  await page.getByLabel("任务状态筛选").selectOption("");
  await expect(page.locator(".task-table tbody tr")).toHaveCount(3);
  pass("Filtering clears selection");
  await page.getByLabel("搜索任务").fill("");
  await expect.poll(() => page.locator(".task-table tbody tr").count()).toBeGreaterThan(3);
  await select(jobs[0]).check();
  const next = page.getByRole("button", { name: "下一页", exact: true });
  if (await next.isEnabled()) {
    await next.click();
    await expect(page.getByText("已选 0 项", { exact: true })).toBeVisible();
    pass("Pagination clears selection");
  }
  await page.getByLabel("搜索任务").fill(prefix);
  await expect(page.locator(".task-table tbody tr")).toHaveCount(3);
  await all.check();
  await page.screenshot({ path: resolve(root, "artifacts/tasks-batch-list.png"), fullPage: true });
  const themeToggle = page.getByRole("button", { name: "切换深色模式", exact: true });
  if (await themeToggle.count()) await themeToggle.click();
  await page.getByRole("button", { name: "卡片视图", exact: true }).click();
  await page.screenshot({ path: resolve(root, "artifacts/tasks-batch-dark.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "看板视图", exact: true }).click();
  await expect
    .poll(() => page.locator(".sidebar").evaluate((el) => el.getBoundingClientRect().right))
    .toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: resolve(root, "artifacts/tasks-batch-mobile.png"),
    fullPage: true,
  });
  pass("Dark mode and mobile board display batch controls without overflow");
  // Simulate a transport failure before the server sees the request; keep the same confirmation for retry.
  await page.route("**/api/jobs/batch-delete", (route) => route.abort(), { times: 1 });
  await batch.click();
  await dialog.getByRole("button", { name: "确认批量删除" }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "确认批量删除" })).toBeEnabled();
  pass("Network failure preserves confirmation and enables retry");
  const assets = await Promise.all(
    jobs.map(async (j) => (await api(`/jobs/${j.id}`)).result.asset_id)
  );
  const [response] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/jobs/batch-delete") && r.request().method() === "POST"
    ),
    dialog.getByRole("button", { name: "确认批量删除" }).click(),
  ]);
  expect(new Set(response.request().postDataJSON().job_ids)).toEqual(
    new Set(jobs.map((j) => j.id))
  );
  expect((await response.json()).deleted_ids).toHaveLength(3);
  await expect(page.getByRole("status")).toContainText("已删除 3 项，跳过 0 项");
  await expect(page.getByText("没有匹配的任务", { exact: true })).toBeVisible();
  await expect(batch).toBeDisabled();
  pass("Confirmed batch deletes only the selected sample records and refreshes results");
  for (const asset of assets) {
    expect((await api(`/assets/${asset}`)).job_id).toBeNull();
    expect((await context.request.get(`${base}/api/assets/${asset}/download`)).status()).toBe(200);
  }
  pass("All output files remain downloadable after batch deletion");
  expect(errors).toEqual([]);
  pass("No uncaught browser errors");
  await writeFile(
    resolve(root, "artifacts/tasks-batch-check.json"),
    JSON.stringify({ checks, errors }, null, 2)
  );
} finally {
  // Only this run's sample IDs can be cleaned up. Retain generated sample files for inspection.
  if (jobs.length)
    await context.request
      .post(`${base}/api/jobs/batch-delete`, { data: { job_ids: jobs.map((j) => j.id) } })
      .catch(() => {});
  if (originalPreferences?.mode)
    await context.request
      .put(`${base}/api/me/preferences`, { data: originalPreferences })
      .catch(() => {});
  await context.request.post(`${base}/api/auth/logout`).catch(() => {});
  await browser.close();
}
