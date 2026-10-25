// Isolated browser fixture: no Google account, database, worker or external API.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);

const origin = "http://127.0.0.1:18367";
const folder = path.resolve(".cache/authentication-polling/browser");
fs.mkdirSync(folder, { recursive: true });
const owner = "00000000-0000-0000-0000-000000000001";
const snapshot = {
  environment: "test",
  generated_at: new Date().toISOString(),
  actor_id: owner,
  workspace_id: null,
  workspaces: [],
  node_counts: {},
  job_counts: {},
  agent_counts: {
    enabled_versions: 0,
    disabled_versions: 0,
    active_versions: 0,
    compatible_online_versions: null,
  },
  nodes: [],
  jobs: [],
  agents: [],
  models: [],
  events: { items: [], total: 0, offset: 0, limit: 25 },
  totals: { nodes: 0, jobs: 0, agents: 0 },
  limit: 25,
  offset: 0,
  metrics: { recent_attempts: [] },
  permissions: [],
  capabilities: [],
  runtimes: [],
  toolchains: [],
};

(async () => {
  const child = spawn(
    process.execPath,
    [
      path.resolve("node_modules/next/dist/bin/next"),
      "start",
      path.resolve("apps/dashboard"),
      "-p",
      "18367",
      "-H",
      "127.0.0.1",
    ],
    {
      stdio: "pipe",
      env: {
        ...process.env,
        GODFATHER_WEB_ORIGIN: origin,
        NEXT_TELEMETRY_DISABLED: "1",
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
      child.on("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.on("exit", (code) => {
        clearTimeout(timer);
        reject(new Error(`Dashboard stopped (${code})`));
      });
    });
    browser = await chromium.launch({
      headless: true,
      ...(process.platform === "win32" ? { channel: "msedge" } : {}),
    });
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let signedIn = true;
    const requests = [];
    await page.route("**/api/control/**", async (route) => {
      const url = new URL(route.request().url());
      const routePath = url.pathname.replace("/api/control/", "");
      requests.push({ path: routePath, method: route.request().method() });
      if (!signedIn)
        return route.fulfill({
          status: 401,
          json: { detail: "Session expired" },
        });
      if (routePath === "auth/me")
        return route.fulfill({
          json: {
            id: owner,
            display_name: "Fixture owner",
            email: "fixture@example.invalid",
            roles: ["platform_admin"],
          },
        });
      if (routePath === "command-center")
        return route.fulfill({ json: snapshot });
      if (routePath === "appearance") return route.fulfill({ json: {} });
      return route.fulfill({
        status: 404,
        json: { detail: "Fixture route unavailable" },
      });
    });
    await page.route("**/downloads/manifest.json", (route) =>
      route.fulfill({ json: { artifacts: [] } }),
    );
    await page.clock.install();
    await page.goto(origin);
    await page
      .getByRole("heading", { name: "Cluster state", exact: true })
      .waitFor();
    await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
    const identityCalls = requests.filter(
      (request) => request.path === "auth/me",
    ).length;
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes("/api/control/command-center") &&
          response.status() === 200,
      ),
      page.clock.runFor(3000),
    ]);
    assert.equal(
      requests.filter((request) => request.path === "auth/me").length,
      identityCalls,
    );

    async function expire() {
      signedIn = false;
      await Promise.all([
        page.waitForResponse(
          (response) =>
            response.url().includes("/api/control/command-center") &&
            response.status() === 401,
        ),
        page.clock.runFor(3000),
      ]);
      await page
        .getByRole("button", { name: "Check session", exact: true })
        .waitFor();
      assert.equal(
        await page
          .getByRole("heading", { name: "Cluster state", exact: true })
          .count(),
        0,
      );
      assert.equal(
        await page
          .getByRole("button", { name: "Sign out", exact: true })
          .count(),
        0,
      );
      const pausedAt = requests.length;
      await page.clock.runFor(120000);
      assert.equal(
        requests.length,
        pausedAt,
        "expired polling must remain stopped",
      );
    }

    await expire();
    const pausedAt = requests.length;
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().endsWith("/api/control/auth/me") &&
          response.status() === 401,
      ),
      page.evaluate(() => window.dispatchEvent(new Event("focus"))),
    ]);
    await page.clock.runFor(120000);
    assert.deepEqual(requests.slice(pausedAt), [
      { path: "auth/me", method: "GET" },
    ]);
    await page.screenshot({
      path: path.join(folder, "session-expired.png"),
      fullPage: true,
    });

    signedIn = true;
    await page
      .getByRole("button", { name: "Check session", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Cluster state", exact: true })
      .waitFor();
    await expire();
    signedIn = true;
    await page.evaluate(() => {
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page
      .getByRole("heading", { name: "Cluster state", exact: true })
      .waitFor();
    assert.ok(
      requests.every((request) => request.method === "GET"),
      "recovery must never replay a write",
    );
    assert.deepEqual(errors, []);
    const result = {
      passed: true,
      checks: [
        "no recurring healthy identity timer",
        "401 hides cached protected views",
        "no protected polling while expired",
        "failed focus verification stays paused",
        "explicit session recovery",
        "focus recovery",
        "no replayed writes",
      ],
      pageErrors: errors,
    };
    fs.writeFileSync(
      path.join(folder, "result.json"),
      JSON.stringify(result, null, 2),
    );
    console.log(
      "Authentication polling browser acceptance passed (fixture responses; no real sign-in).",
    );
  } finally {
    if (browser) await browser.close();
    child.kill();
    log.end();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
