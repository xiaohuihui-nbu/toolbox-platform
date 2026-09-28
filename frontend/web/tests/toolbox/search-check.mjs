import { chromium, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
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
  errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  await page.goto(base);
  await page.getByLabel("账号", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "进入工作空间" }).click();
  await page.getByRole("button", { name: "视频下载", exact: true }).click();
  await page.getByLabel("视频搜索关键词").fill("Sintel 预告片");
  await page
    .locator(".video-search-bar")
    .getByRole("button", { name: "搜索", exact: true })
    .click();
  await expect(page.locator(".video-search-card").first()).toBeVisible({ timeout: 100000 });
  const titles = await page.locator(".search-card-body h3").allTextContents();
  await page.locator(".search-cover input").nth(0).check();
  await page.locator(".search-cover input").nth(1).check();
  await expect(page.getByText("已选 2 个视频", { exact: true })).toBeVisible();
  await page.screenshot({ path: resolve(root, "artifacts/video-search.png"), fullPage: true });
  const [response] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/api/video-downloads/batch") && r.request().method() === "POST"
    ),
    page.getByRole("button", { name: "批量下载", exact: true }).click(),
  ]);
  const batch = await response.json();
  expect(batch.accepted).toBe(2);
  expect(batch.items.map((item) => item.job.title)).toEqual(
    titles.slice(0, 2).map((title) => title.slice(0, 160))
  );
  const jobs = [];
  for (const item of batch.items) {
    await expect
      .poll(
        async () => {
          const job = await (await context.request.get(`${base}/api/jobs/${item.job.id}`)).json();
          return ["succeeded", "failed", "cancelled"].includes(job.state);
        },
        { timeout: 180000, intervals: [2000] }
      )
      .toBe(true);
    jobs.push(await (await context.request.get(`${base}/api/jobs/${item.job.id}`)).json());
  }
  expect(errors).toEqual([]);
  await page.screenshot({
    path: resolve(root, "artifacts/video-search-batch.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: resolve(root, "artifacts/video-search-mobile.png"),
    fullPage: true,
  });
  await writeFile(
    resolve(root, "artifacts/search-ui.json"),
    JSON.stringify({ titles, jobs, errors }, null, 2)
  );
  console.log(
    JSON.stringify({
      search_results: titles.length,
      selected_submitted: batch.accepted,
      outcomes: jobs.map((job) => ({ title: job.title, state: job.state, message: job.message })),
      errors,
    })
  );
  await context.request.post(`${base}/api/auth/logout`);
} finally {
  await browser.close();
}
