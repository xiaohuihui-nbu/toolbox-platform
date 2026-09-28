import { chromium, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve("../.."), base = "http://127.0.0.1:18990";
const password = (await readFile(resolve(root, ".env"), "utf8")).match(/^TB_ADMIN_PASSWORD=(.+)$/m)[1].trim();
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext();
const page = await context.newPage();
try {
  expect((await context.request.post(`${base}/api/auth/login`, { data: { username: "admin", password } })).ok()).toBe(true);
  await page.route("**/api/video-search", route => route.fulfill({ status: 202, json: { id: "search-error-fixture", state: "queued" } }));
  await page.route("**/api/video-search/search-error-fixture", route => route.fulfill({ json: { id: "search-error-fixture", state: "failed", error: "B站拒绝了搜索请求（HTTP 412），请稍后重试；也可粘贴视频链接尝试下载", items: [] } }));
  await page.goto(base);
  await page.getByRole("button", { name: "打开视频下载", exact: true }).click();
  await page.getByLabel("视频搜索关键词").fill("音乐 & 舞蹈");
  await page.locator(".video-search-bar").getByRole("button", { name: "搜索", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("HTTP 412");
  await expect(page.getByText("本次搜索未完成，请查看下方提示后重试。", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "到B站搜索，复制链接后下载" })).toHaveAttribute("href", "https://search.bilibili.com/all?keyword=" + encodeURIComponent("音乐 & 舞蹈"));
  await expect(page.getByRole("button", { name: "批量下载", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "粘贴链接", exact: true }).click();
  await expect(page.getByLabel("视频链接", { exact: true })).toBeVisible();
  console.log("PASS simulated 412 reason, failure state, encoded source search link and paste-link fallback");
} finally {
  await context.request.post(`${base}/api/auth/logout`).catch(() => {});
  await browser.close();
}
