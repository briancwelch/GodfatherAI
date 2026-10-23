// Browser fixture only: no real account, provider key, generation or database writes.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);
const ts = require("typescript");
const appearance = { exports: {} };
new Function(
  "module",
  "exports",
  ts.transpileModule(
    fs.readFileSync("apps/dashboard/src/lib/appearance.ts", "utf8"),
    { compilerOptions: { module: ts.ModuleKind.CommonJS } },
  ).outputText,
)(appearance, appearance.exports);
const folder = path.resolve(".cache/image-workspace-fix/browser");
fs.mkdirSync(folder, { recursive: true });
const id = (n) => `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`;
const workspace = id(1),
  node = id(2),
  connection = id(3),
  job = id(4);
let enabled = false,
  canEnable = true,
  rejectAllow = true;
const grants = [],
  jobs = [];
const models = [
  "gpt-image-1",
  "gpt-image-1-mini",
  "gpt-image-1.5",
  "gpt-image-2",
  "gpt-image-2-2026-04-21",
  "gpt-image-2.5-sunburst",
  "gpt-image-2.5-sunburst-2026-09-08",
  "gpt-image-2.5-flare",
  "gpt-image-2.5-flare-2026-09-08",
];
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const route = url.pathname.replace(/^\/api\/v1\//, "");
  let body = "";
  for await (const chunk of req) body += chunk;
  let data;
  if (route === "auth/me")
    data = {
      id: id(10),
      display_name: "Fixture owner",
      roles: ["platform_admin"],
    };
  else if (route === "appearance") data = appearance.exports.defaults;
  else if (route === "command-center")
    data = {
      environment: "test",
      generated_at: new Date().toISOString(),
      workspace_id: workspace,
      workspaces: [{ id: workspace, name: "Restricted workspace" }],
      nodes: [],
      jobs: [],
      models: [],
      node_counts: {},
      job_counts: {},
      agents: [],
      events: [],
      capabilities: [],
      runtimes: [],
      toolchains: [],
      permissions: ["jobs.submit", "nodes.contribute"],
    };
  else if (route === "workloads/options") {
    const choices = models.map((model) => ({
      node_id: node,
      node_name: "Fixture computer",
      available: true,
      provider: "openai",
      provider_id: "account-images",
      model,
      connection_id: connection,
      workspace_allowed: enabled && model === "gpt-image-1.5",
      can_enable: canEnable,
    }));
    data = {
      workspace_name: "Restricted workspace",
      cloud_image_models: choices.filter((m) => m.workspace_allowed),
      restricted_cloud_image_models: choices.filter(
        (m) => !m.workspace_allowed,
      ),
      nodes: [
        {
          id: node,
          name: "Fixture computer",
          available: true,
          analytics: false,
          image_models: [],
          cloud_image_models: enabled ? ["OpenAI: gpt-image-1.5"] : [],
          restricted_image_model_count: enabled ? 8 : 9,
        },
      ],
      sql_note: "",
    };
  } else if (route === "models/workspace-access" && req.method === "POST") {
    grants.push(JSON.parse(body));
    if (rejectAllow || !canEnable) {
      res.statusCode = 403;
      data = { detail: "Fixture workspace permission denied" };
    } else {
      enabled = true;
      data = { enabled: true };
    }
  } else if (route === "workloads/jobs" && req.method === "POST") {
    jobs.push(JSON.parse(body));
    res.statusCode = 201;
    data = { id: job };
  } else {
    res.statusCode = 404;
    data = { detail: "Fixture route unavailable" };
  }
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(data));
});
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const origin = "http://127.0.0.1:18366";
  const child = spawn(
    process.execPath,
    [
      path.resolve("node_modules/next/dist/bin/next"),
      "start",
      path.resolve("apps/dashboard"),
      "-p",
      "18366",
      "-H",
      "127.0.0.1",
    ],
    {
      stdio: "pipe",
      env: {
        ...process.env,
        GODFATHER_API_URL: `http://127.0.0.1:${server.address().port}`,
        GODFATHER_WEB_ORIGIN: origin,
      },
    },
  );
  const log = fs.createWriteStream(path.join(folder, "server.log"));
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error("Dashboard startup timeout")),
        30000,
      );
      child.stdout.on("data", (data) => {
        if (data.toString().includes("Ready in")) {
          clearTimeout(timer);
          resolve();
        }
      });
      child.on("error", reject);
    });
    browser = await chromium.launch({ headless: true, channel: "msedge" });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1050 },
    });
    await context.addCookies([
      { name: "godfather_session", value: "x".repeat(43), url: origin },
    ]);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/downloads/manifest.json", (route) =>
      route.fulfill({ json: { artifacts: [] } }),
    );
    await page.goto(`${origin}/images`);
    await page
      .getByText("Restricted workspace has not allowed an image model", {
        exact: false,
      })
      .waitFor();
    assert.equal(
      await page.getByLabel("Provider", { exact: true }).inputValue(),
      "openai",
    );
    assert.equal(
      await page
        .getByLabel("My cloud model and computer")
        .locator("option")
        .count(),
      10,
    );
    assert.doesNotMatch(
      await page.locator("main section").first().innerText(),
      /advertises a configured local image model|No image models/,
    );
    await page
      .getByLabel("Image prompt", { exact: true })
      .fill("Keep this prompt while allowing the model");
    await page
      .getByLabel("My cloud model and computer")
      .selectOption(`${connection}|gpt-image-1.5`);
    const allow = page.getByRole("button", {
      name: "Allow selected model in workspace",
      exact: true,
    });
    await allow.click();
    await page
      .getByRole("status")
      .filter({ hasText: "Fixture workspace permission denied" })
      .first()
      .waitFor();
    assert.equal(jobs.length, 0);
    assert.equal(enabled, false);
    rejectAllow = false;
    for (const [theme, width] of [
      ["light", 1440],
      ["dark", 390],
    ]) {
      await page
        .getByRole("combobox", { name: "Theme", exact: true })
        .selectOption(theme);
      await page.setViewportSize({ width, height: 1050 });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await page.screenshot({
        path: path.join(folder, `restricted-${theme}.png`),
        fullPage: true,
      });
    }
    await allow.click();
    await page
      .getByRole("status")
      .filter({ hasText: "Model allowed in this workspace" })
      .first()
      .waitFor();
    assert.deepEqual(grants[1], {
      workspace_id: workspace,
      node_id: node,
      provider_id: "account-images",
      identifier: "gpt-image-1.5",
    });
    assert.equal(
      await page.getByLabel("Image prompt", { exact: true }).inputValue(),
      "Keep this prompt while allowing the model",
    );
    assert.equal(jobs.length, 0);
    const generate = page.getByRole("button", {
      name: "Generate image",
      exact: true,
    });
    await generate.click();
    assert.equal(jobs.length, 0);
    await page
      .getByRole("checkbox", { name: /accept provider charges/ })
      .check();
    await generate.click();
    assert.equal(jobs.length, 0);
    await page
      .getByRole("checkbox", { name: /processing this data or prompt/ })
      .check();
    await page.route(`**/jobs/${job}`, (route) =>
      route.fulfill({
        contentType: "text/html",
        body: "Fixture job submitted; no inference executed",
      }),
    );
    await generate.click();
    await page.waitForURL(`${origin}/jobs/${job}`);
    assert.equal(jobs.length, 1);
    assert.equal(jobs[0].paid_consent, true);
    assert.equal(jobs[0].input.image.model, "gpt-image-1.5");
    assert.equal(jobs[0].connection_id, connection);
    enabled = false;
    canEnable = false;
    await page.goto(`${origin}/images`);
    await page
      .getByLabel("My cloud model and computer")
      .selectOption(`${connection}|gpt-image-1.5`);
    await page
      .getByText("Ask a workspace owner or administrator", { exact: false })
      .waitFor();
    assert.equal(
      await page
        .getByRole("button", {
          name: "Allow selected model in workspace",
          exact: true,
        })
        .count(),
      0,
    );
    assert.equal(
      await page
        .getByRole("button", { name: "Generate image", exact: true })
        .isDisabled(),
      true,
    );
    await page.getByLabel("Provider", { exact: true }).selectOption("gemini");
    await page
      .getByText("No accessible Google Gemini image model", { exact: false })
      .waitFor();
    await page
      .getByLabel("Provider", { exact: true })
      .selectOption("automatic1111");
    await page.getByRole("button", { name: "Refresh", exact: true }).click();
    await page
      .getByText("No online computer has a permitted local image model", {
        exact: false,
      })
      .waitFor();
    assert.equal(
      await page.getByLabel("Provider", { exact: true }).inputValue(),
      "automatic1111",
    );
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(folder, "result.json"),
      JSON.stringify(
        {
          passed: true,
          checks: [
            "restricted inventory remains visible",
            "workspace-specific blocker",
            "explicit model-only authorization",
            "rejected authorization remains actionable",
            "prompt preserved",
            "member cannot grant",
            "paid and worker consent required before submission",
            "no automatic generation",
            "provider-specific messages",
            "explicit local choice survives refresh",
            "desktop/light and mobile/dark layouts",
          ],
          pageErrors: errors,
        },
        null,
        2,
      ),
    );
    console.log(
      "Image workspace authorization browser acceptance passed (fixture API; no paid calls).",
    );
  } finally {
    if (browser) await browser.close();
    child.kill();
    server.close();
    log.end();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
