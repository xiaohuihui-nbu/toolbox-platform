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
  results = [],
  errors = [];
page.on("pageerror", (error) => errors.push(error.message));
try {
  const login = await context.request.post(`${base}/api/auth/login`, {
    data: { username: "admin", password },
  });
  expect(login.ok()).toBe(true);
  await page.goto(base);
  await page.getByRole("button", { name: "打开视频下载", exact: true }).click();
  for (const [platform, query] of [
    ["bilibili", "舞蹈"],
    ["bilibili", "音乐"],
    ["youtube", "Blender Sintel trailer"],
  ]) {
    await page.getByLabel("搜索平台").selectOption(platform);
    await page.getByLabel("视频搜索关键词").fill(query);
    const start = Date.now();
    await page
      .locator(".video-search-bar")
      .getByRole("button", { name: "搜索", exact: true })
      .click();
    await expect(
      page.locator(".video-search-bar").getByRole("button", { name: "搜索", exact: true })
    ).toBeEnabled({ timeout: 65000 });
    if (!(await page.locator(".video-search-card").count())) {
      const result = {
        platform,
        query,
        count: 0,
        error: await page.locator(".video-downloader .error").innerText(),
        elapsed_ms: Date.now() - start,
      };
      results.push(result);
      console.log(JSON.stringify(result));
      await expect(
        page.getByText("本次搜索未完成，请查看下方提示后重试。", { exact: true })
      ).toBeVisible();
      continue;
    }
    await expect(page.locator(".search-cover input").first()).not.toBeChecked();
    const count = await page.locator(".video-search-card").count();
    expect(count).toBeGreaterThanOrEqual(2);
    await page.locator(".search-cover input").nth(0).check();
    await page.locator(".search-cover input").nth(1).check();
    await expect(page.getByText("已选 2 个视频", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "批量下载", exact: true })).toBeEnabled();
    const thumbnail = page.locator(".search-cover img").first();
    if (platform === "bilibili") {
      await expect(thumbnail).toBeVisible();
      await expect
        .poll(() => thumbnail.evaluate((img) => img.complete && img.naturalWidth > 0))
        .toBe(true);
      await page.screenshot({ path: resolve(root, "artifacts/search-fixed.png"), fullPage: true });
    }
    const result = { platform, query, count, elapsed_ms: Date.now() - start };
    results.push(result);
    console.log(JSON.stringify(result));
  }
  expect(errors).toEqual([]);
  await writeFile(
    resolve(root, "artifacts/search-regression.json"),
    JSON.stringify({ results, errors }, null, 2)
  );
  expect(
    results.every((result) => result.count > 0),
    "All live searches return results"
  ).toBe(true);
} finally {
  await context.request.post(`${base}/api/auth/logout`).catch(() => {});
  await browser.close();
}
