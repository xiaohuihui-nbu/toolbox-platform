import { chromium, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve("../.."),
  base = "http://127.0.0.1:18990";
const secret = (await readFile(resolve(root, ".env"), "utf8"))
  .match(/^TB_ADMIN_PASSWORD=(.+)$/m)[1]
  .trim();
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1050 },
  locale: "zh-CN",
});
const page = await context.newPage(),
  errors = [],
  checks = [];
page.on("pageerror", (e) => errors.push(e.message));
let job;
const pass = (label) => {
  checks.push(label);
  console.log("PASS " + label);
};
try {
  await page.goto(base);
  await page.getByLabel("账号", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill(secret);
  await page.getByRole("button", { name: "进入工作空间" }).click();
  await page.getByRole("button", { name: "任务中心", exact: true }).click();
  await page.getByRole("button", { name: "新建任务", exact: true }).first().click();
  await page
    .getByRole("dialog", { name: "新建任务", exact: true })
    .getByRole("button", { name: /文本导出/ })
    .click();
  await page.getByLabel("文本内容", { exact: true }).fill("任务增删改查界面验收样例。");
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST"),
    page.getByRole("button", { name: "开始处理", exact: true }).click(),
  ]);
  job = await response.json();
  await page.getByRole("button", { name: "查看任务进度" }).click();
  await page.getByLabel("搜索任务", { exact: true }).fill(job.id);
  await expect(page.locator(".task-table tbody tr")).toHaveCount(1);
  pass("Create task from task center and query by ID");
  await expect
    .poll(
      async () => (await (await context.request.get(`${base}/api/jobs/${job.id}`)).json()).state,
      { timeout: 40000 }
    )
    .toBe("succeeded");
  const title = "验收任务 " + job.id.slice(0, 8);
  await page.getByRole("button", { name: "编辑 文本导出", exact: true }).click();
  await page.getByLabel("任务名称", { exact: true }).fill(title);
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.getByRole("button", { name: title, exact: true })).toBeVisible();
  pass("Rename completed task and refresh persisted title");
  await page.getByRole("button", { name: title, exact: true }).click();
  await page
    .getByRole("dialog", { name: "任务详情", exact: true })
    .getByText("查看输入参数")
    .click();
  await expect(
    page.getByRole("dialog", { name: "任务详情", exact: true }).locator("pre")
  ).toContainText("任务增删改查");
  await page.getByLabel("关闭任务详情", { exact: true }).click();
  pass("Task details show input snapshot and output");
  for (const [name, selector] of [
    ["卡片视图", ".task-card-grid"],
    ["看板视图", ".task-board"],
    ["列表视图", ".task-table"],
  ]) {
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.locator(selector)).toBeVisible();
    pass(name + " renders filtered task");
  }
  await page.getByLabel("任务状态筛选").selectOption("failed");
  await expect(page.getByText("没有匹配的任务", { exact: true })).toBeVisible();
  await page.getByLabel("任务状态筛选").selectOption("");
  await expect(page.locator(".task-table tbody tr")).toHaveCount(1);
  await page.getByLabel("搜索任务").fill("");
  await expect.poll(() => page.locator(".task-table tbody tr").count()).toBeGreaterThan(1);
  await page.screenshot({ path: resolve(root, "artifacts/tasks-list.png"), fullPage: true });
  await page.getByRole("button", { name: "卡片视图", exact: true }).click();
  await page.screenshot({ path: resolve(root, "artifacts/tasks-cards.png"), fullPage: true });
  await page.getByRole("button", { name: "看板视图", exact: true }).click();
  await expect(page.locator(".task-board")).toBeVisible();
  await page.screenshot({ path: resolve(root, "artifacts/tasks-board.png"), fullPage: true });
  await page.reload();
  await expect(page.getByRole("button", { name: "看板视图", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  pass("View preference survives reload");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.locator(".sidebar").evaluate((el) => el.getBoundingClientRect().right))
    .toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: resolve(root, "artifacts/tasks-mobile.png"), fullPage: true });
  pass("Mobile board has no horizontal overflow");
  await page.getByLabel("搜索任务").fill(job.id);
  await expect(page.locator(".task-card")).toHaveCount(1);
  await page.getByRole("button", { name: `删除 ${title}`, exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByText("没有匹配的任务", { exact: true })).toBeVisible();
  expect((await context.request.get(`${base}/api/jobs/${job.id}`)).status()).toBe(404);
  pass("Delete task after confirmation");
  expect(errors).toEqual([]);
  pass("No uncaught browser errors");
  await writeFile(
    resolve(root, "artifacts/tasks-check.json"),
    JSON.stringify({ checks, errors }, null, 2)
  );
  await context.request.post(`${base}/api/auth/logout`);
} finally {
  await browser.close();
}
