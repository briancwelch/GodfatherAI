// Isolated UI acceptance. Fixtures never connect to the production API or Google.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const { spawn } = require("node:child_process");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);
const folder = path.resolve(".cache/command-center-management");
fs.mkdirSync(folder, { recursive: true });
const uuid = (n) => `00000000-0000-0000-0000-${String(n).padStart(12, "0")}`;
const owner = uuid(1),
  workspace = uuid(2),
  agent = uuid(3);
const account = {
  id: owner,
  email: "owner@example.invalid",
  display_name: "Isolated owner",
  roles: ["platform_admin"],
  permissions: ["platform.manage", "nodes.contribute"],
  enabled: true,
  picture: null,
};
const accounts = Array.from({ length: 27 }, (_, i) => ({
  ...account,
  id: uuid(100 + i),
  email: `user-${i}@example.invalid`,
  display_name: `Fixture ${i}`,
  roles: ["contributor"],
  permissions: ["nodes.contribute"],
}));
const roles = new Map(
  accounts.map((a, i) => [a.id, i === 26 ? "admin" : "member"]),
);
let jobs = Array.from({ length: 26 }, (_, i) => ({
  id: uuid(300 + i),
  owner_id: owner,
  workspace_id: workspace,
  type: "inference.text",
  status: "COMPLETED",
  priority: 0,
  attempt_count: 1,
  fencing_token: 1,
  checkpoint_ref: null,
  created_at: new Date().toISOString(),
  cancel_requested_at: null,
  assigned_node_id: null,
}));
let agents = [1, 2].map((version) => ({
  id: agent,
  version_id: uuid(400 + version),
  owner_id: owner,
  workspace_id: workspace,
  version,
  enabled: false,
  definition: {
    name: "Fixture agent",
    requirements: {},
    allowed_tools: [],
    permissions: [],
    workflow: { steps: [] },
  },
}));
let deletedWorkspace = false,
  deletes = [],
  platformSave = null,
  archiveStart = null,
  archiveFinish = null,
  archiveFailure = false,
  heldAccess = null,
  holdUser = null;
const memberPage = {
  owner_id: owner,
  shared: true,
  allowed_models: [],
  allowed_tools: [],
  limit: 25,
  total: 27,
  offset: 0,
  members: accounts
    .slice(0, 25)
    .map((a) => ({ user_id: a.id, role: roles.get(a.id) })),
};
const ts = require("typescript");
const appearanceSource = fs.readFileSync(
  "apps/dashboard/src/lib/appearance.ts",
  "utf8",
);
const appearanceModule = { exports: {} };
new Function(
  "module",
  "exports",
  ts.transpileModule(appearanceSource, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
)(appearanceModule, appearanceModule.exports);
let siteAppearance = structuredClone(appearanceModule.exports.defaults);
let computers = [1, 2, 3].map((i) => ({
  id: uuid(600 + i),
  name: `Fixture computer ${i}`,
  revoked: i === 3,
  node_id: uuid(600 + i),
}));
const nodeFixture = {
  node_id: uuid(601),
  owner_id: owner,
  owner_name: "Isolated owner",
  name: "Fixture computer 1",
  os: "windows",
  os_version: "11",
  architecture: "x86_64",
  worker_version: "0.4.1-rc.3",
  state: "online",
  connection_status: "online",
  protocol_version: 1,
  last_heartbeat_at: new Date().toISOString(),
  resources: {
    source: "simulated",
    cpu_name: "Fixture CPU",
    cpu_count: 4,
    ram_bytes: 8000000000,
    gpus: [],
  },
  primary_capabilities: [],
  secondary_capabilities: [],
  runtimes: [],
  toolchains: [],
  dependencies: [],
  sandbox_modes: [],
  worker_tools: [],
  tool_permissions: [],
  installed_models: [],
  model_deployments: [],
  scheduling_policy: "shared",
  concurrency_limit: 1,
  visible_active_jobs: 0,
};
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const route = url.pathname.replace("/api/v1/", "");
  const offset = Number(url.searchParams.get("offset") || 0);
  let body = "";
  for await (const chunk of req) body += chunk;
  const payload = body ? JSON.parse(body) : null;
  res.setHeader("Content-Type", "application/json");
  let value;
  if (route === "auth/me") value = account;
  else if (route === "appearance") {
    if (req.method === "POST") siteAppearance = payload;
    value = siteAppearance;
  } else if (route === "administration/node-credentials")
    value = {
      items: computers.slice(offset, offset + 25),
      offset,
      limit: 25,
      total: computers.length,
    };
  else if (route === "administration/audit")
    value = {
      items: [
        {
          id: uuid(750),
          actor_id: owner,
          actor_name: "Isolated owner",
          action: "security.appearance_updated",
          timestamp: new Date().toISOString(),
          details: {},
          correlation_id: "fixture",
        },
      ],
      offset: 0,
      limit: 25,
      total: 1,
    };
  else if (route === "tools") value = [];
  else if (route === "command-center")
    value = {
      environment: "test",
      generated_at: new Date().toISOString(),
      actor_id: owner,
      workspace_id: deletedWorkspace ? null : workspace,
      workspaces: deletedWorkspace
        ? []
        : [
            {
              id: workspace,
              name: "Product research",
              owner_id: owner,
              can_manage: true,
            },
          ],
      nodes: [nodeFixture],
      jobs: jobs.slice(offset, offset + 25),
      agents,
      models: [],
      events: { items: [], total: 0, offset: 0, limit: 25 },
      release: { version: null, revision: null, built_at: null },
      node_counts: {},
      job_counts: { COMPLETED: jobs.length },
      agent_counts: {},
      totals: { jobs: jobs.length, nodes: 1, agents: agents.length },
      limit: 25,
      offset,
    };
  else if (route === "administration/users")
    value = {
      items: accounts.slice(offset, offset + 25),
      offset,
      limit: 25,
      total: 27,
    };
  else if (
    route === `administration/workspaces/${workspace}/members` &&
    req.method === "GET"
  )
    value = {
      ...memberPage,
      offset,
      members: accounts
        .slice(offset, offset + 25)
        .map((a) => ({ user_id: a.id, role: roles.get(a.id) })),
    };
  else if (route === `administration/workspaces/${workspace}/members`) {
    roles.set(payload.user_id, payload.role);
    value = { updated: true };
  } else if (
    route.startsWith(`administration/workspaces/${workspace}/members/`)
  ) {
    const user = route.split("/").at(-1);
    value = {
      user_id: user,
      role: roles.get(user) || "none",
      account: accounts.find((a) => a.id === user),
    };
    if (user === holdUser) {
      heldAccess = () => res.end(JSON.stringify(value));
      return;
    }
  } else if (
    route.startsWith("administration/users/") &&
    req.method === "POST"
  ) {
    platformSave = payload;
    const a = accounts.find((a) => a.id === route.split("/").at(-1));
    Object.assign(a, { roles: payload.roles, enabled: payload.enabled });
    value = a;
  } else if (route === "models/install-options") value = { catalog: [] };
  else if (route === "agent-options")
    value = {
      models: [],
      tools: [],
      workflows: [],
      capabilities: [],
      model_limit: 200,
      repositories: [],
    };
  else if (route === "administration/bulk-delete") {
    deletes.push(payload);
    if (payload.kind === "node-credentials")
      computers = computers.filter((c) => !payload.ids.includes(c.id));
    if (payload.kind === "jobs")
      jobs = jobs.filter((j) => !payload.ids.includes(j.id));
    if (payload.kind === "agents")
      agents = agents.filter((a) => !payload.ids.includes(a.id));
    if (payload.kind === "workspaces") deletedWorkspace = true;
    value = { deleted_ids: payload.ids };
  } else if (route === "administration/workspace-archive") {
    if (archiveFailure) {
      res.statusCode = 503;
      res.end(
        JSON.stringify({
          detail: "A fixture artifact is unavailable; nothing deleted",
        }),
      );
      return;
    }
    const data = Buffer.alloc(65536, 1);
    res.setHeader("Content-Type", "application/zip");
    res.setHeader("Content-Length", data.length);
    res.setHeader(
      "Content-Disposition",
      'attachment; filename="godfather-workspaces-fixture.zip"',
    );
    archiveStart = () => {
      res.flushHeaders();
      res.write(data.subarray(0, 32768));
    };
    archiveFinish = () => res.end(data.subarray(32768));
    return;
  } else {
    res.statusCode = 404;
    value = { detail: "Isolated fixture route unavailable" };
  }
  res.end(JSON.stringify(value));
});
(async () => {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const apiPort = server.address().port,
    webPort = 18350,
    origin = `http://127.0.0.1:${webPort}`;
  const child = spawn(
    process.execPath,
    [
      path.resolve("node_modules/next/dist/bin/next"),
      "start",
      path.resolve("apps/dashboard"),
      "-p",
      String(webPort),
      "-H",
      "127.0.0.1",
    ],
    {
      stdio: "pipe",
      env: {
        ...process.env,
        GODFATHER_API_URL: `http://127.0.0.1:${apiPort}`,
        GODFATHER_WEB_ORIGIN: origin,
      },
    },
  );
  const log = fs.createWriteStream(path.join(folder, "browser-server.log"));
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  let browser;
  try {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(
        () => reject(new Error("Dashboard startup timed out")),
        30000,
      );
      child.stdout.on("data", (data) => {
        if (data.toString().includes("Ready in")) {
          clearTimeout(timeout);
          resolve();
        }
      });
      child.on("error", reject);
      child.on("exit", (code) => reject(new Error(`Dashboard exited ${code}`)));
    });
    browser = await chromium.launch({ headless: true, channel: "msedge" });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      acceptDownloads: true,
    });
    await context.addCookies([
      { name: "godfather_session", value: "x".repeat(43), url: origin },
    ]);
    const page = await context.newPage();
    await page.route("**/downloads/manifest.json", (route) =>
      route.fulfill({
        json: {
          artifacts: [
            {
              filename: "consigliere-0.4.1-rc.4-windows-x64-setup.exe",
              sha256: "a".repeat(64),
              signing: "Fixture unsigned",
            },
          ],
        },
      }),
    );
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("dialog", (d) => d.accept());
    await page.goto(origin + "/jobs");
    await page.getByRole("table").waitFor();
    assert.equal(
      await page
        .getByRole("button", { name: "Next page", exact: true })
        .count(),
      2,
    );
    await page
      .getByRole("button", { name: "Next page", exact: true })
      .first()
      .click();
    await page.getByText("26", { exact: false }).first().waitFor();
    await page
      .getByRole("checkbox", { name: `Select job ${uuid(325)}`, exact: true })
      .check();
    const timeOrigin = await page.evaluate(() => performance.timeOrigin);
    await page
      .getByRole("button", { name: "Delete selected", exact: true })
      .click();
    const simple = page.getByRole("dialog");
    assert.equal(
      await simple.getByText("Archive & download", { exact: true }).count(),
      0,
    );
    await simple
      .getByRole("button", { name: "Confirm delete selected", exact: true })
      .click();
    await simple.waitFor({ state: "hidden" });
    assert.equal(deletes[0].kind, "jobs");
    assert.deepEqual(deletes[0].ids, [uuid(325)]);
    assert.equal(await page.evaluate(() => performance.timeOrigin), timeOrigin);
    await page.goto(origin + "/agents");
    await page
      .getByRole("checkbox", { name: /Select agent Fixture agent/ })
      .first()
      .check();
    await page.getByText("1 selected on this page", { exact: true }).waitFor();
    await page
      .getByRole("button", { name: "Delete selected", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm delete selected", exact: true })
      .click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.deepEqual(deletes.at(-1), { kind: "agents", ids: [agent] });
    await page.goto(origin + "/administration");
    await page.getByRole("tab", { name: "Permissions", exact: true }).click();
    await page
      .getByRole("combobox", { name: "Workspace", exact: true })
      .selectOption(workspace);
    const editor = page.getByRole("region", {
      name: "Selected user permissions",
    });
    const picker = editor.locator(".account-picker");
    await picker
      .getByRole("button", { name: "Next page", exact: true })
      .first()
      .click();
    await picker
      .getByRole("option", { name: "user-26@example.invalid", exact: true })
      .waitFor({ state: "attached" });
    await picker.getByRole("combobox").selectOption(accounts[26].id);
    await editor
      .getByText("Current workspace access: Workspace administrator", {
        exact: true,
      })
      .waitFor();
    assert.equal(
      await editor
        .getByRole("checkbox", { name: "contributor", exact: true })
        .isChecked(),
      true,
    );
    await editor
      .getByRole("combobox", { name: "Workspace role", exact: true })
      .selectOption("member");
    await editor
      .getByRole("button", { name: "Save workspace access", exact: true })
      .click();
    await editor
      .getByText("Current workspace access: Member", { exact: true })
      .waitFor();
    await editor
      .getByRole("checkbox", { name: "platform admin", exact: true })
      .check();
    await editor
      .getByRole("button", {
        name: "Save platform access and revoke sessions",
        exact: true,
      })
      .click();
    await editor.getByText("Permissions saved.", { exact: true }).waitFor();
    assert.deepEqual(
      new Set(platformSave.roles),
      new Set(["contributor", "platform_admin"]),
    );
    await picker
      .getByRole("button", { name: "Previous page", exact: true })
      .first()
      .click();
    holdUser = accounts[0].id;
    const held = page.waitForRequest((r) =>
      r.url().includes(`/members/${holdUser}?`),
    );
    await picker.getByRole("combobox").selectOption(holdUser);
    await held;
    await picker.getByRole("combobox").selectOption(accounts[1].id);
    await editor
      .locator("p")
      .filter({ hasText: /^user-1@example.invalid$/ })
      .waitFor();
    heldAccess();
    holdUser = null;
    assert.equal(
      await editor
        .getByRole("combobox", { name: "Workspace role", exact: true })
        .inputValue(),
      "member",
    );
    await page.getByRole("tab", { name: "Workspaces", exact: true }).click();
    await page
      .getByRole("checkbox", {
        name: "Select workspace Product research",
        exact: true,
      })
      .check();
    await page
      .getByRole("button", { name: "Delete selected", exact: true })
      .click();
    const popup = page.getByRole("dialog", {
      name: "Keep a copy before you go",
      exact: true,
    });
    await popup.waitFor();
    assert.equal(
      await popup
        .getByRole("button", { name: "Delete workspaces", exact: true })
        .isDisabled(),
      true,
    );
    await popup
      .getByRole("button", { name: "Archive & download", exact: true })
      .click();
    await popup
      .getByText("Preparing your archive...", { exact: true })
      .waitFor();
    assert.equal(
      await popup.getByRole("progressbar").getAttribute("value"),
      null,
    );
    await page.screenshot({
      path: path.join(folder, "archive-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.screenshot({
      path: path.join(folder, "archive-mobile.png"),
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      true,
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    archiveStart();
    await popup
      .getByText("Downloading your archive...", { exact: true })
      .waitFor();
    const downloadEvent = page.waitForEvent("download");
    archiveFinish();
    const download = await downloadEvent;
    await download.saveAs(path.join(folder, "ui-fixture-archive.zip"));
    await popup
      .getByText(
        "Archive received and handed to your browser. Verify the ZIP is saved before deleting.",
        { exact: true },
      )
      .waitFor();
    assert.equal(deletes.filter((d) => d.kind === "workspaces").length, 0);
    await popup
      .getByRole("button", { name: "Delete workspaces", exact: true })
      .click();
    await popup.waitFor({ state: "hidden" });
    assert.equal(deletes.at(-1).kind, "workspaces");
    // Failure never auto-deletes; skipping requires an explicit choice.
    deletedWorkspace = false;
    archiveFailure = true;
    await page.reload();
    await page.getByRole("tab", { name: "Workspaces", exact: true }).click();
    await page
      .getByRole("checkbox", {
        name: "Select workspace Product research",
        exact: true,
      })
      .check();
    await page
      .getByRole("button", { name: "Delete selected", exact: true })
      .click();
    await popup
      .getByRole("button", { name: "Archive & download", exact: true })
      .click();
    await popup.getByRole("alert").waitFor();
    assert.equal(
      await popup
        .getByRole("button", { name: "Delete workspaces", exact: true })
        .isDisabled(),
      true,
    );
    await popup.getByRole("checkbox").check();
    assert.equal(
      await popup
        .getByRole("button", { name: "Delete workspaces", exact: true })
        .isDisabled(),
      false,
    );
    await popup
      .getByRole("button", { name: "Keep workspaces", exact: true })
      .click();
    // Overview fragment commands use the shared icon set.
    await page.goto(origin + "/");
    await page.getByRole("region", { name: "Overview ribbon" }).waitFor();
    assert.equal(
      await page.locator('.application-ribbon a[href="/jobs"] svg').count(),
      1,
    );
    assert.equal(
      await page.locator('.application-ribbon a[href="/nodes"] svg').count(),
      1,
    );
    await page.goto(origin + "/nodes");
    const ownerName = page.locator(".owner-name").first();
    await ownerName.waitFor();
    await ownerName.hover();
    assert.equal(await ownerName.getAttribute("title"), owner);
    assert.equal(await ownerName.getByRole("tooltip").isVisible(), true);
    await page.getByText("Out of Date", { exact: true }).waitFor();
    const tooltipBox = await ownerName.getByRole("tooltip").boundingBox();
    const tableBox = await page.locator(".table-scroll").boundingBox();
    assert.ok(
      tooltipBox.y >= tableBox.y &&
        tooltipBox.y + tooltipBox.height <= tableBox.y + tableBox.height,
      "Tooltip fits within the scrolling table",
    );
    await page.screenshot({
      path: path.join(folder, "nodes-identity-and-version.png"),
    });
    await page.goto(origin + "/administration/appearance");
    const appearancePanel = page.getByRole("region", {
      name: "Site appearance",
      exact: true,
    });
    await appearancePanel
      .getByRole("button", { name: "Save site appearance", exact: true })
      .waitFor();
    await appearancePanel
      .getByLabel("Font size (px)", { exact: true })
      .fill("15");
    await appearancePanel
      .getByLabel("Striped table rows", { exact: true })
      .check();
    const appearanceOrigin = await page.evaluate(() => performance.timeOrigin);
    await appearancePanel
      .getByRole("button", { name: "Save site appearance", exact: true })
      .click();
    await appearancePanel
      .getByRole("status")
      .filter({ hasText: "Site appearance saved" })
      .waitFor();
    assert.equal(siteAppearance.font_size, 15);
    assert.equal(siteAppearance.striped_tables, true);
    assert.equal(
      await page.evaluate(() => performance.timeOrigin),
      appearanceOrigin,
    );
    assert.equal(
      await page.evaluate(() => getComputedStyle(document.body).fontSize),
      "15px",
    );
    await page.screenshot({
      path: path.join(folder, "appearance-desktop.png"),
    });
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.screenshot({ path: path.join(folder, "appearance-mobile.png") });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.reload();
    await page
      .getByRole("region", { name: "Site appearance", exact: true })
      .getByLabel("Font size (px)", { exact: true })
      .waitFor();
    assert.equal(
      await page
        .getByRole("region", { name: "Site appearance", exact: true })
        .getByLabel("Font size (px)", { exact: true })
        .inputValue(),
      "15",
    );
    await page.getByRole("tab", { name: "Computers", exact: true }).click();
    await page
      .getByRole("checkbox", { name: "Select Fixture computer 1", exact: true })
      .check();
    await page
      .getByRole("checkbox", { name: "Select Fixture computer 2", exact: true })
      .check();
    const computerOrigin = await page.evaluate(() => performance.timeOrigin);
    await page
      .getByRole("button", { name: "Delete selected", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm delete selected", exact: true })
      .click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.deepEqual(deletes.at(-1), {
      kind: "node-credentials",
      ids: [uuid(601), uuid(602)],
    });
    assert.equal(
      await page.evaluate(() => performance.timeOrigin),
      computerOrigin,
    );
    await page
      .getByRole("button", { name: "Delete credential", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm delete credential", exact: true })
      .click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
    assert.equal(computers.length, 0);
    assert.equal(
      await page.evaluate(() => performance.timeOrigin),
      computerOrigin,
    );
    await page.getByRole("tab", { name: "Audit", exact: true }).click();
    const auditPanel = page.getByRole("tabpanel", {
      name: "Audit",
      exact: true,
    });
    const auditActor = auditPanel.locator(".owner-name");
    await auditActor.waitFor();
    assert.equal(await auditActor.getAttribute("title"), owner);
    await auditActor.focus();
    assert.equal(await auditActor.getByRole("tooltip").isVisible(), true);
    assert.ok((await auditActor.textContent()).includes("Isolated owner"));
    await page.screenshot({
      path: path.join(folder, "audit-actor-tooltip.png"),
    });
    assert.deepEqual(errors, []);
    const result = {
      audit_actor_tooltip: true,
      owner_tooltip: true,
      worker_outdated: true,
      overview_icons: true,
      appearance_save_and_reload: true,
      computer_single_and_bulk_ajax: true,
      jobs_ajax: true,
      agents_all_versions: true,
      top_bottom_pagination: true,
      exact_permissions_beyond_member_page: true,
      preserved_platform_roles: true,
      stale_user_response_ignored: true,
      archive_progress_and_download: true,
      archive_failure_no_deletion: true,
      explicit_skip: true,
      desktop_mobile_layout: true,
      errors,
    };
    fs.writeFileSync(
      path.join(folder, "browser-result.json"),
      JSON.stringify(result, null, 2),
    );
    console.log(JSON.stringify(result));
  } finally {
    if (browser) await browser.close();
    child.kill();
    server.closeAllConnections();
    await new Promise((r) => server.close(r));
    log.end();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
