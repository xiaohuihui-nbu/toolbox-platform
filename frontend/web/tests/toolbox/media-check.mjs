import { chromium, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve("../.."),
  output = resolve(root, "artifacts");
await mkdir(output, { recursive: true });
const password = (await readFile(resolve(root, ".env"), "utf8"))
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
page.on("pageerror", (error) => errors.push(error.message));
const passed = (label) => {
  checks.push(label);
  console.log("PASS " + label);
};
const url = "http://127.0.0.1:18990";
try {
  await page.goto(url);
  await page.getByLabel("账号", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "进入工作空间" }).click();
  await page.getByRole("button", { name: "AI 自然配音", exact: true }).click();
  await expect(page.getByText("GPT-SoVITS · CPU 已就绪", { exact: true })).toBeVisible({
    timeout: 15000,
  });
  await expect(page.locator(".tool-form select").first().locator("option")).toHaveCount(16);
  passed("GPT-SoVITS ready and 16 voices available");
  const reference = page.getByLabel("音色参考试听");
  await reference.evaluate((el) => el.play());
  await expect.poll(() => reference.evaluate((el) => el.currentTime)).toBeGreaterThan(0.2);
  await reference.evaluate((el) => el.pause());
  passed("Reference voice audio plays");
  await page.getByLabel("配音文案").fill("你好，欢迎使用拾光工具箱。");
  await page.screenshot({
    path: resolve(output, "natural-tts-form.png"),
    fullPage: true,
  });
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST"),
    page.getByRole("button", { name: "开始处理", exact: true }).click(),
  ]);
  const natural = await response.json();
  await expect
    .poll(
      async () => (await (await context.request.get(`${url}/api/jobs/${natural.id}`)).json()).state,
      { timeout: 300000, intervals: [2000] }
    )
    .toBe("succeeded");
  const result = await (await context.request.get(`${url}/api/jobs/${natural.id}`)).json();
  expect(result.result.provider).toBe("gptsovits");
  expect(result.result.provider_job_id).toMatch(/^[a-f0-9]{32}$/);
  const audio = page.getByLabel("语音试听", { exact: true });
  await expect(audio).toBeVisible({ timeout: 10000 });
  await audio.evaluate((el) => el.play());
  await expect.poll(() => audio.evaluate((el) => el.currentTime)).toBeGreaterThan(0.2);
  await audio.evaluate((el) => el.pause());
  await page.screenshot({
    path: resolve(output, "natural-tts-result.png"),
    fullPage: true,
  });
  passed("Real GPT-SoVITS synthesis stored privately and plays in result panel");
  await page.getByLabel("关闭工具", { exact: true }).click();
  await page.getByRole("button", { name: "视频下载", exact: true }).click();
  await page.getByRole("button", { name: "粘贴链接", exact: true }).click();
  await page
    .getByLabel("视频链接")
    .fill("https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4");
  const [videoResponse] = await Promise.all([
    page.waitForResponse(
      (r) => r.url().endsWith("/api/video-downloads/batch") && r.request().method() === "POST"
    ),
    page.getByRole("button", { name: "批量下载", exact: true }).click(),
  ]);
  const videoJob = (await videoResponse.json()).items[0].job;
  await expect
    .poll(
      async () =>
        (await (await context.request.get(`${url}/api/jobs/${videoJob.id}`)).json()).state,
      { timeout: 150000, intervals: [2000] }
    )
    .toBe("succeeded");
  await page.getByRole("button", { name: "预览", exact: true }).click();
  const video = page.getByLabel("视频预览", { exact: true });
  await expect(video).toBeVisible({ timeout: 10000 });
  await expect.poll(() => video.evaluate((el) => el.readyState)).toBeGreaterThan(0);
  await video.evaluate(async (el) => {
    el.currentTime = 10;
    await el.play();
  });
  await expect.poll(() => video.evaluate((el) => el.currentTime)).toBeGreaterThan(10.2);
  await video.evaluate((el) => el.pause());
  passed("Downloaded video plays and seeks through authenticated Range endpoint");
  await page.screenshot({
    path: resolve(output, "video-preview.png"),
    fullPage: true,
  });
  await page.getByLabel("关闭工具", { exact: true }).click();
  await page.getByRole("button", { name: "文件中心", exact: true }).click();
  await page.getByRole("button", { name: "预览视频", exact: true }).first().click();
  await expect(page.getByRole("dialog", { name: "文件预览" }).getByLabel("视频预览")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileVideo = page.getByRole("dialog", { name: "文件预览" }).getByLabel("视频预览");
  await expect.poll(() => mobileVideo.evaluate((el) => el.readyState)).toBeGreaterThan(0);
  await mobileVideo.evaluate(async (el) => {
    el.currentTime = 10;
    await el.play();
  });
  await expect.poll(() => mobileVideo.evaluate((el) => el.currentTime)).toBeGreaterThan(10.2);
  await mobileVideo.evaluate((el) => el.pause());
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
  ).toBeTruthy();
  await page.screenshot({
    path: resolve(output, "video-preview-mobile.png"),
    fullPage: true,
  });
  passed("File-center preview and mobile dialog layout work");
  expect(errors).toEqual([]);
  passed("No browser runtime errors");
  await context.request.post(`${url}/api/auth/logout`);
  await writeFile(
    resolve(output, "media-check.json"),
    JSON.stringify(
      { checks, errors, natural_job_id: natural.id, video_job_id: videoJob.id },
      null,
      2
    )
  );
} finally {
  await browser.close();
}
