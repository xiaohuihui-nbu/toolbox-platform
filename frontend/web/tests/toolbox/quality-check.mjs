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
const page = await context.newPage();
try {
  await page.goto(base);
  await page.getByLabel("账号", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "进入工作空间" }).click();
  await page.getByRole("button", { name: "视频下载", exact: true }).click();
  await page.getByRole("button", { name: "粘贴链接", exact: true }).click();
  await page.getByLabel("视频链接").fill("https://www.bilibili.com/video/av117322685618746");
  await page.getByLabel("下载清晰度", { exact: true }).selectOption("720p");
  const [response] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/api/video-downloads/batch") && r.request().method() === "POST"
    ),
    page.getByRole("button", { name: "批量下载", exact: true }).click(),
  ]);
  expect(response.request().postDataJSON().quality).toBe("720p");
  const batch = await response.json();
  expect(batch.accepted).toBe(1);
  let job;
  await expect
    .poll(
      async () => {
        job = await (await context.request.get(`${base}/api/jobs/${batch.items[0].job.id}`)).json();
        return job.state;
      },
      { timeout: 150000, intervals: [2000] }
    )
    .toBe("succeeded");
  await page.getByRole("button", { name: "预览", exact: true }).click();
  const video = page.getByLabel("视频预览", { exact: true });
  await expect.poll(() => video.evaluate((el) => el.videoHeight)).toBe(720);
  await video.evaluate(async (el) => {
    el.currentTime = 10;
    await el.play();
  });
  await expect.poll(() => video.evaluate((el) => el.currentTime)).toBeGreaterThan(10.2);
  await video.evaluate((el) => el.pause());
  const asset = await (
    await context.request.get(`${base}/api/assets/${job.result.asset_id}`)
  ).json();
  await page.screenshot({ path: resolve(root, "artifacts/download-quality.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const result = {
    quality: "720p",
    height: 720,
    bytes: asset.size,
    job: job.id,
    playback: "passed",
    mobile: "passed",
  };
  await writeFile(resolve(root, "artifacts/quality-ui.json"), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  await context.request.post(`${base}/api/auth/logout`);
} finally {
  await browser.close();
}
