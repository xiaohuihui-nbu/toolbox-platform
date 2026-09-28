import { chromium, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const root = resolve("../.."),
  artifacts = resolve(root, "artifacts");
await mkdir(artifacts, { recursive: true });
const env = await readFile(resolve(root, ".env"), "utf8");
const secret = env.match(/^TB_ADMIN_PASSWORD=(.+)$/m)?.[1].trim();
assert(secret, "Initial administrator credential is required for local verification");
const browser = await chromium.launch({ channel: "msedge", headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1040 },
  deviceScaleFactor: 1,
  locale: "zh-CN",
  reducedMotion: "reduce",
});
const page = await context.newPage();
const errors = [],
  checks = [];
page.on("pageerror", (e) => errors.push(e.message));
const check = (value, message) => {
  assert(value, message);
  checks.push(message);
  console.log("PASS " + message);
};
try {
  await page.goto("http://127.0.0.1:18990");
  await page.getByRole("heading", { name: "登录你的工作空间" }).waitFor();
  await page.screenshot({
    path: resolve(artifacts, "login.png"),
    fullPage: true,
  });
  await page.getByLabel("账号", { exact: true }).fill("admin");
  await page.getByLabel("密码", { exact: true }).fill(secret);
  await page.getByRole("button", { name: "进入工作空间" }).click();
  await page.getByRole("heading", { name: "好工具，让想法轻松发生." }).waitFor();
  await page.getByRole("button", { name: "偏好设置", exact: true }).click();
  await page.getByRole("button", { name: "浅色模式", exact: true }).click();
  await page.getByRole("button", { name: "日落珊瑚", exact: true }).click();
  await page.getByRole("button", { name: "工具工作台", exact: true }).click();
  check((await page.locator(".tool-card").count()) === 7, "Seven real tool cards loaded");
  await page.screenshot({
    path: resolve(artifacts, "workspace-light.png"),
    fullPage: true,
  });
  if (await page.getByRole("button", { name: "收藏JSON 格式化", exact: true }).count())
    await page.getByRole("button", { name: "收藏JSON 格式化", exact: true }).click();
  await page.getByRole("button", { name: /我的收藏/ }).click();
  await expect(page.getByRole("heading", { name: "喜欢的工具，随时就绪" })).toBeVisible();
  await expect(page.getByRole("button", { name: "JSON 格式化", exact: true })).toBeVisible();
  check(
    (await page.locator(".tool-card").count()) ===
      (await page.locator(".tool-card button.saved").count()),
    "Favorite filters tool catalog"
  );
  await page.getByRole("button", { name: "JSON 格式化", exact: true }).click();
  await page.getByLabel("输入内容").fill('{"hello":"你好","count":2}');
  await page.getByRole("button", { name: "格式化", exact: true }).click();
  check(
    (await page.getByLabel("处理结果").inputValue()).includes('\n  "hello": "你好"'),
    "JSON formatter handles Unicode"
  );
  await page.getByLabel("关闭工具", { exact: true }).click();
  await page.getByRole("button", { name: "工具工作台", exact: true }).click();
  await page.getByRole("button", { name: "Base64 编解码", exact: true }).click();
  await page.getByLabel("输入内容").fill("你好 Toolbox");
  await page.getByRole("button", { name: "编码", exact: true }).click();
  const encoded = await page.getByLabel("处理结果").inputValue();
  await page.getByLabel("输入内容").fill(encoded);
  await page.getByRole("button", { name: "解码", exact: true }).click();
  check(
    (await page.getByLabel("处理结果").inputValue()) === "你好 Toolbox",
    "Base64 Unicode round trip"
  );
  await page.getByLabel("关闭工具", { exact: true }).click();
  await page.getByRole("button", { name: "文字转语音", exact: true }).click();
  await page.getByLabel("朗读内容").fill("你好，欢迎来到拾光工具箱。把时间留给创造。");
  const [submittedResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST"),
    page.getByRole("button", { name: "开始处理", exact: true }).click(),
  ]);
  const submittedJob = await submittedResponse.json();
  await page.getByRole("heading", { name: "已加入任务队列" }).waitFor();
  await page.getByRole("button", { name: "查看任务进度", exact: true }).click();
  await expect
    .poll(
      async () =>
        (
          await (
            await context.request.get(`http://127.0.0.1:18990/api/jobs/${submittedJob.id}`)
          ).json()
        ).state,
      { timeout: 60000 }
    )
    .toBe("succeeded");
  await page
    .getByRole("row")
    .filter({ hasText: submittedJob.id.slice(0, 8) })
    .getByRole("link", { name: "下载", exact: true })
    .waitFor({ timeout: 10000 });
  check(true, "TTS submitted through UI and result became downloadable");
  await page.screenshot({
    path: resolve(artifacts, "tasks.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "文件中心", exact: true }).click();
  await page.getByRole("link", { name: "下载文件", exact: true }).first().waitFor();
  await page.screenshot({
    path: resolve(artifacts, "files.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "偏好设置", exact: true }).click();
  await page.getByRole("button", { name: "深色模式", exact: true }).click();
  await page.getByRole("button", { name: "暮色鸢尾", exact: true }).click();
  await page.waitForFunction(
    () =>
      document.documentElement.dataset.theme === "dark" &&
      document.documentElement.dataset.accent === "violet"
  );
  await page.screenshot({
    path: resolve(artifacts, "appearance-dark.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "工具工作台", exact: true }).click();
  await page.screenshot({
    path: resolve(artifacts, "workspace-dark.png"),
    fullPage: true,
  });
  await expect
    .poll(
      async () =>
        (await (await context.request.get("http://127.0.0.1:18990/api/me")).json()).preferences
    )
    .toMatchObject({ mode: "dark", accent: "violet" });
  await page.reload();
  await page.getByRole("heading", { name: "好工具，让想法轻松发生." }).waitFor();
  check(
    (await page.locator("html").getAttribute("data-theme")) === "dark",
    "Dark mode persists after reload"
  );
  await page.getByRole("button", { name: "偏好设置", exact: true }).click();
  await page.getByRole("button", { name: "跟随系统", exact: true }).click();
  await page.emulateMedia({ colorScheme: "light" });
  await page.waitForFunction(() => document.documentElement.dataset.theme === "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.waitForFunction(() => document.documentElement.dataset.theme === "dark");
  check(true, "System mode follows OS appearance changes");
  for (const [label, key] of [
    ["日落珊瑚", "coral"],
    ["晴空蔚蓝", "blue"],
    ["薄荷森林", "green"],
    ["暮色鸢尾", "violet"],
  ]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    check(
      (await page.locator("html").getAttribute("data-accent")) === key,
      `Accent ${key} applies`
    );
  }
  await page.getByRole("button", { name: "浅色模式", exact: true }).click();
  await page.getByRole("button", { name: "日落珊瑚", exact: true }).click();
  await page.getByRole("button", { name: "工具工作台", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await context.request.get("http://127.0.0.1:18990/api/me")).json()).preferences
    )
    .toMatchObject({ mode: "light", accent: "coral" });
  await page.screenshot({
    path: resolve(artifacts, "workspace-light.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: resolve(artifacts, "workspace-mobile.png"),
    fullPage: true,
  });
  check(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    "Mobile has no horizontal overflow"
  );
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await page.getByRole("button", { name: "文件中心", exact: true }).click();
  check(
    await page.getByRole("heading", { name: "每一份成果，妥善安放." }).isVisible(),
    "Mobile navigation works"
  );
  check(errors.length === 0, "No uncaught browser errors");
  await context.request.post("http://127.0.0.1:18990/api/auth/logout");
  await writeFile(
    resolve(artifacts, "browser-check.json"),
    JSON.stringify({ passed: checks.length, checks, errors }, null, 2),
    "utf8"
  );
} finally {
  await browser.close();
}
