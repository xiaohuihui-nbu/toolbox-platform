import { chromium, expect } from "@playwright/test";
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve("../.."), base = "http://127.0.0.1:18990";
const password = (await readFile(resolve(root, ".env"), "utf8")).match(/^TB_ADMIN_PASSWORD=(.+)$/m)[1].trim();
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
const page = await context.newPage(), checks = [], errors = [];
page.on("pageerror", error => errors.push(error.message));
const pass = message => { checks.push(message); console.log("PASS " + message); };
const play = async video => {
  await expect.poll(() => video.evaluate(el => el.readyState), { timeout: 20000 }).toBeGreaterThan(0);
  await video.evaluate(async el => { el.muted = true; el.currentTime = 2; await el.play(); });
  await expect.poll(() => video.evaluate(el => el.currentTime)).toBeGreaterThan(2.2);
  await video.evaluate(el => el.pause());
};
try {
  expect((await context.request.post(`${base}/api/auth/login`, { data: { username: "admin", password } })).ok()).toBe(true);
  const assets = await (await context.request.get(`${base}/api/assets`)).json();
  const jobs = await (await context.request.get(`${base}/api/jobs/query?state=succeeded&tool_id=video.download&page_size=24`)).json();
  const job = jobs.items.find(job => assets.some(asset => asset.id === job.result.asset_id && asset.preview_kind === "video"));
  expect(job, "Existing completed video is available for read-only playback verification").toBeTruthy();
  await page.goto(base + "/#jobs");
  await page.getByLabel("搜索任务", { exact: true }).fill(job.id);
  for (const mode of ["列表视图", "卡片视图", "看板视图"]) {
    await page.getByRole("button", { name: mode, exact: true }).click();
    // Wait for the debounced ID search; several jobs may share the same title.
    await expect(page.getByRole("button", { name: `预览 ${job.title}`, exact: true })).toHaveCount(1);
    await page.getByRole("button", { name: `预览 ${job.title}`, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "播放预览", exact: true });
    await expect(dialog).toBeVisible();
    await play(dialog.getByLabel("视频预览", { exact: true }));
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    pass(mode + " directly previews and seeks an existing video; Escape closes player");
  }
  await page.getByRole("button", { name: "工具工作台", exact: true }).click();
  await page.getByRole("button", { name: "打开视频下载", exact: true }).click();
  await page.getByRole("button", { name: "粘贴链接", exact: true }).click();
  const source = "https://example.com/already-downloaded.mp4";
  await page.getByLabel("视频链接", { exact: true }).fill(source);
  // Only the receipt is simulated; the player loads an actual existing, authenticated asset.
  await page.route("**/api/v1/toolbox/video-downloads/batch", route => route.fulfill({ json: { items: [{ url: source, state: "accepted", job }] } }), { times: 1 });
  await page.getByRole("button", { name: "批量下载", exact: true }).click();
  await page.getByRole("button", { name: "预览", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "播放预览", exact: true });
  await play(dialog.getByLabel("视频预览", { exact: true }));
  await page.screenshot({ path: resolve(root, "artifacts/preview-restored.png") });
  await page.getByLabel("关闭播放预览", { exact: true }).click();
  await expect(page.getByRole("dialog", { name: "视频下载", exact: true })).toBeVisible();
  pass("Download receipt opens visible player above download dialog and returns correctly");
  await page.getByRole("button", { name: "查看已下载文件与播放预览", exact: true }).click();
  await expect(page).toHaveURL(/#\/?files$/);
  await page.getByRole("button", { name: "预览视频", exact: true }).first().click();
  await page.setViewportSize({ width: 390, height: 844 });
  await play(page.getByRole("dialog", { name: "文件预览" }).getByLabel("视频预览"));
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  pass("Downloaded-files shortcut and mobile file-center playback work");
  expect(errors).toEqual([]);
  await writeFile(resolve(root, "artifacts/preview-entry-check.json"), JSON.stringify({ checks, errors }, null, 2));
} finally {
  await context.request.post(`${base}/api/auth/logout`).catch(() => {});
  await browser.close();
}
