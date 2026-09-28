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
  viewport: { width: 1440, height: 1080 },
  locale: "zh-CN",
  reducedMotion: "reduce",
});
const page = await context.newPage(),
  checks = [],
  errors = [];
const pass = (message) => {
  checks.push(message);
  console.log("PASS " + message);
};
const shot = async (name) => {
  await page.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  );
  await page.screenshot({
    path: resolve(root, `artifacts/studio-${name}.png`),
    fullPage: true,
    animations: "disabled",
  });
};
const noOverflow = async () =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
page.on("pageerror", (error) => errors.push(error.message));
let preferences;
try {
  await page.goto(base);
  await expect(page.getByRole("heading", { name: "登录你的工作空间" })).toBeVisible();
  await shot("login");
  const login = await context.request.post(`${base}/api/auth/login`, {
    data: { username: "admin", password },
  });
  expect(login.ok()).toBeTruthy();
  preferences = (await login.json()).preferences;
  // The user explicitly chose the dark blue/violet studio appearance. Preserve favorites.
  await context.request.put(`${base}/api/me/preferences`, {
    data: { ...preferences, mode: "dark", accent: "blue", favorites: preferences.favorites || [] },
  });
  await page.reload();
  await expect(page.locator(".featured-workspace")).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const catalog = await (await context.request.get(`${base}/api/tools`)).json();
  await expect(page.locator(".tool-card")).toHaveCount(catalog.filter((tool) => tool.enabled).length);
  await noOverflow();
  await shot("home-dark");
  pass("Dark studio loads real tools and both featured entries");
  await page.getByRole("button", { name: "打开视频下载", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "视频下载", exact: true })).toBeVisible();
  await page.getByLabel("搜索平台").selectOption("youtube");
  await expect(page.getByLabel("YouTube 免登录说明")).toBeVisible();
  await shot("youtube");
  pass("Video shortcut opens downloader; YouTube anonymous limits explained");
  await page.getByRole("button", { name: "粘贴链接", exact: true }).click();
  await page
    .getByLabel("视频链接", { exact: true })
    .fill("https://www.youtube.com/watch?v=BFjrd7IdNrM");
  await expect(page.getByLabel("YouTube 免登录说明")).toBeVisible();
  await page.getByLabel("视频链接", { exact: true }).fill("https://youtube.com.evil.example/video");
  await expect(page.getByLabel("YouTube 免登录说明")).toHaveCount(0);
  await page
    .getByLabel("视频链接", { exact: true })
    .fill("https://www.youtube.com/watch?v=BFjrd7IdNrM");
  pass("YouTube link detection uses hostname boundaries");
  await page.route(
    "**/api/v1/toolbox/video-downloads/batch",
    (route) =>
      route.fulfill({
        json: {
          items: [
            {
              url: "https://www.youtube.com/watch?v=BFjrd7IdNrM",
              state: "accepted",
              job: {
                id: "ui-auth-fixture",
                title: "YouTube 访问验证示例",
                state: "failed",
                message: "源站要求登录验证，当前免登录模式无法下载此视频。",
                result: { error_code: "authentication_required" },
              },
            },
          ],
        },
      }),
    { times: 1 }
  );
  await page.getByRole("button", { name: "批量下载", exact: true }).click();
  await expect(page.getByRole("link", { name: "在 YouTube 查看原视频" })).toHaveAttribute(
    "href",
    "https://www.youtube.com/watch?v=BFjrd7IdNrM"
  );
  await expect(
    page.getByText("源站要求登录验证，当前免登录模式无法下载此视频。", { exact: true })
  ).toBeVisible();
  pass("Simulated authentication failure displays reason and safe source link");
  await page.getByLabel("关闭工具", { exact: true }).click();
  await page.getByRole("button", { name: "试试文字转语音", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("关闭工具", { exact: true }).click();
  await page.getByRole("button", { name: /个进行中任务/ }).click();
  await expect(page.getByLabel("当前页任务概览")).toBeVisible();
  await page.getByRole("button", { name: "卡片视图", exact: true }).click();
  await shot("tasks");
  pass("TTS and task shortcuts work; page-scoped task counts are labeled");
  for (const [label, key] of [
    ["深海蓝", "blue"],
    ["暮色鸢尾", "violet"],
    ["日落珊瑚", "coral"],
    ["森林绿", "green"],
  ]) {
    await page.getByRole("button", { name: "偏好设置", exact: true }).click();
    // Theme labels are sourced from the application; choose by the color class if copy changes.
    await page.locator(`.accent-options button:has(.${key})`).click();
    await expect(page.locator("html")).toHaveAttribute("data-accent", key);
    await page.getByRole("button", { name: "工具工作台", exact: true }).click();
    await noOverflow();
  }
  pass("All four accent themes remain available");
  await page.getByRole("button", { name: "切换浅色模式", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await shot("home-light");
  pass("Light mode remains readable and functional");
  await page.getByRole("button", { name: "偏好设置", exact: true }).click();
  await page.locator(".accent-options button:has(.blue)").click();
  await page.getByRole("button", { name: "深色模式", exact: true }).click();
  await page.getByRole("button", { name: "工具工作台", exact: true }).click();
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await expect
      .poll(() => page.locator(".sidebar").evaluate((el) => el.getBoundingClientRect().right))
      .toBeLessThanOrEqual(1);
    await noOverflow();
    await shot(`home-${width}`);
  }
  pass("Tablet and phone layouts have no horizontal overflow");
  await page.getByRole("button", { name: "打开视频下载", exact: true }).click();
  await page.getByLabel("搜索平台").selectOption("youtube");
  await noOverflow();
  await shot("youtube-mobile");
  await page.getByLabel("关闭工具", { exact: true }).click();
  pass("Mobile download dialog supports YouTube notice and controls");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-accent", "blue");
  expect(errors).toEqual([]);
  pass("Chosen dark blue appearance persists; no browser errors");
  await writeFile(
    resolve(root, "artifacts/studio-check.json"),
    JSON.stringify({ checks, errors }, null, 2)
  );
} finally {
  if (preferences)
    await context.request.put(`${base}/api/me/preferences`, {
      data: preferences,
    });
  await context.request.post(`${base}/api/auth/logout`).catch(() => {});
  await browser.close();
}
