// Only scripts.check_google_oidc starts this test against isolated godfather_test.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
let playwright;
try {
  playwright = require(process.env.GODFATHER_PLAYWRIGHT_MODULE || "playwright");
} catch {
  playwright = require(path.resolve(".tools/browser/node_modules/playwright"));
}
const origin = "http://127.0.0.1:3010";
const folder = process.argv[2];
const model = process.argv[3];
const wait = async (predicate, timeout = 180000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Integration condition timed out");
};
(async () => {
  const browser = await playwright.chromium.launch({
    headless: true,
    ...(process.platform === "win32" ? { channel: "msedge" } : {}),
  });
  const results = [];
  try {
    async function login(subject, invitation) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
      });
      await context.route("https://accounts.google.com/**", async (route) => {
        const url = new URL(route.request().url());
        const callback = new URL(`${origin}/api/auth/callback`);
        callback.searchParams.set("state", url.searchParams.get("state"));
        callback.searchParams.set(
          "code",
          `${subject}|${url.searchParams.get("nonce")}`,
        );
        assert.equal(url.searchParams.get("scope"), "openid email profile");
        assert.equal(url.searchParams.get("code_challenge_method"), "S256");
        await route.fulfill({
          status: 302,
          headers: { location: callback.href },
          body: "",
        });
      });
      const page = await context.newPage();
      page.on("response", (response) => {
        if (response.url().includes("/api/auth/"))
          console.log(
            "auth HTTP",
            response.status(),
            new URL(response.url()).pathname,
          );
      });
      page.on("pageerror", (e) => {
        throw e;
      });
      await page.goto(origin);
      if (invitation)
        await page
          .getByLabel("Invitation token (first sign-in only)")
          .fill(invitation);
      await page.getByRole("button", { name: "Continue with Google" }).click();
      if (subject !== "outsider-sub") {
        try {
          await page
            .getByRole("button", { name: "Sign out", exact: true })
            .waitFor();
        } catch (error) {
          await page.screenshot({
            path: path.join(folder, "login-failure.png"),
            fullPage: true,
          });
          console.log("Login page:", await page.locator("body").innerText());
          throw error;
        }
      } else
        await page
          .getByText("Sign-in was not authorized.", { exact: false })
          .waitFor();
      return { context, page };
    }
    async function api(context, route, data) {
      const response =
        data === undefined
          ? await context.request.get(`${origin}/api/control/${route}`)
          : await context.request.post(`${origin}/api/control/${route}`, {
              data,
              headers: { Origin: origin },
            });
      assert.ok(
        response.ok(),
        `${route}: ${response.status()} ${await response.text()}`,
      );
      return response.json();
    }
    const first = await login("first-sub");
    const account = await api(first.context, "auth/me");
    assert.deepEqual(account.roles, ["platform_admin"]);
    const cookie = (await first.context.cookies()).find(
      (c) => c.name === "godfather_session",
    );
    assert.ok(cookie.httpOnly && cookie.sameSite === "Strict");
    assert.equal(
      await first.page.evaluate(
        () => localStorage.length + sessionStorage.length,
      ),
      0,
    );
    results.push(
      "Google flow, Authlib verification, bootstrap, real account display and HttpOnly session (Google network mocked)",
    );
    const invite2 = await api(first.context, "administration/invitations", {
      email: "second@example.invalid",
      roles: ["platform_admin"],
    });
    const second = await login("second-sub", invite2.invitation_token);
    const secondUser = await api(second.context, "auth/me");
    assert.deepEqual(secondUser.permissions, account.permissions);
    const invite3 = await api(first.context, "administration/invitations", {
      email: "contributor@example.invalid",
      roles: ["contributor"],
    });
    const contributor = await login(
      "contributor-sub",
      invite3.invitation_token,
    );
    const outsider = await login("outsider-sub");
    assert.equal(
      (
        await outsider.context.request.get(
          `${origin}/api/control/command-center`,
        )
      ).status(),
      401,
    );
    assert.equal(
      (
        await contributor.context.request.get(
          `${origin}/api/control/administration/users`,
        )
      ).status(),
      403,
    );
    await contributor.page.goto(`${origin}/administration`);
    assert.equal(
      await contributor.page
        .getByRole("heading", { name: "Users", exact: true })
        .count(),
      0,
    );
    results.push(
      "independent equal administrators, invited contributor, uninvited denial and permission-aware UI",
    );
    const workspace = await api(first.context, "administration/workspaces", {
      name: "Isolated OIDC real-worker integration",
      allowed_models: [model],
    });
    const privateWorkspace = await api(
      first.context,
      "administration/workspaces",
      { name: "Restricted private workspace" },
    );
    assert.equal(
      (
        await second.context.request.get(
          `${origin}/api/control/command-center?workspace_id=${privateWorkspace.id}`,
        )
      ).status(),
      404,
    );
    await api(
      first.context,
      `administration/workspaces/${workspace.id}/members`,
      { user_id: secondUser.id, role: "admin" },
    );
    const worker = await api(first.context, "administration/node-credentials", {
      name: "Actual Windows OIDC integration worker",
    });
    fs.writeFileSync(
      path.join(folder, "worker.json"),
      JSON.stringify({
        ...worker,
        kind: "worker",
        credential_id: worker.node_id,
      }),
      { mode: 0o600 },
    );
    fs.writeFileSync(
      path.join(folder, "ready.json"),
      JSON.stringify({ workspace_id: workspace.id, node_id: worker.node_id }),
    );
    await wait(async () => {
      const snapshot = await api(first.context, "command-center");
      return snapshot.nodes.some(
        (n) =>
          n.node_id === worker.node_id &&
          n.state === "online" &&
          n.resources.source === "physical",
      );
    });
    await first.page.goto(`${origin}/nodes/${worker.node_id}`);
    await first.page
      .getByRole("heading", {
        name: "Actual Windows OIDC integration worker",
        exact: false,
      })
      .waitFor();
    await first.page.screenshot({
      path: path.join(folder, "physical-node.png"),
      fullPage: true,
    });
    const denial = await second.context.request.post(
      `${origin}/api/control/nodes/${worker.node_id}/control`,
      { data: { action: "enable" }, headers: { Origin: origin } },
    );
    assert.equal(denial.status(), 403);
    results.push(
      "actual worker telemetry and status persisted; other administrator cannot override node owner",
    );
    await first.page.goto(`${origin}/agents`);
    await first.page.locator(".scope-bar select").selectOption(workspace.id);
    await first.page
      .getByRole("button", { name: "Create agent", exact: true })
      .click();
    let editor = first.page.getByRole("dialog", {
      name: "Create agent",
      exact: true,
    });
    await editor
      .getByLabel("Name", { exact: true })
      .fill("Real local model integration");
    await editor
      .getByLabel("Description", { exact: true })
      .fill("Created through the Command Center editor.");
    await editor
      .getByLabel("Model requirement", { exact: false })
      .selectOption(`ollama:${model}`);
    await editor
      .getByRole("button", { name: "Create agent", exact: true })
      .click();
    await editor.waitFor({ state: "hidden" });
    let snapshot = await api(
      first.context,
      `command-center?workspace_id=${workspace.id}&section=agents`,
    );
    let agent = snapshot.agents.find(
      (a) => a.definition.name === "Real local model integration",
    );
    assert.ok(agent && agent.version === 1);
    await first.page
      .getByRole("button", {
        name: "Real local model integration",
        exact: true,
      })
      .click();
    await first.page
      .getByRole("button", { name: "Edit / New version", exact: true })
      .click();
    editor = first.page.getByRole("dialog", {
      name: "Create immutable agent version",
    });
    await editor
      .getByLabel("Description", { exact: true })
      .fill("Version two, original preserved.");
    await editor
      .getByRole("button", { name: "Save new version", exact: true })
      .click();
    await editor.waitFor({ state: "hidden" });
    const versions = await api(first.context, `agents/${agent.id}/versions`);
    assert.equal(versions.length, 2);
    assert.equal(
      versions[0].definition.description,
      "Created through the Command Center editor.",
    );
    agent = versions[1];
    assert.equal(agent.version, 2);
    await first.page
      .getByRole("button", { name: "Disable agent", exact: true })
      .click();
    await first.page
      .getByRole("button", { name: "Confirm disable agent", exact: true })
      .click();
    await first.page
      .getByRole("button", { name: "Enable agent", exact: true })
      .click();
    await first.page
      .getByRole("button", { name: "Confirm enable agent", exact: true })
      .click();
    await first.page
      .getByRole("button", { name: "Run agent", exact: true })
      .waitFor();
    await first.page.screenshot({
      path: path.join(folder, "agent-management-desktop.png"),
      fullPage: true,
    });
    await first.page
      .getByRole("button", { name: "Navigation", exact: true })
      .click();
    assert.equal(
      await first.page
        .getByLabel("Workspace navigation", { exact: true })
        .count(),
      0,
    );
    await first.page
      .getByRole("button", { name: "Navigation", exact: true })
      .click();
    await first.page
      .getByRole("button", { name: "Inspector", exact: true })
      .click();
    assert.equal(
      await first.page
        .getByRole("complementary", {
          name: "Workspace inspector",
          exact: true,
        })
        .count(),
      1,
    );
    await first.page
      .getByRole("button", { name: "Inspector", exact: true })
      .click();
    await first.page
      .getByRole("button", { name: "Run agent", exact: true })
      .click();
    const runDialog = first.page.getByRole("dialog", {
      name: "Run agent",
      exact: true,
    });
    await runDialog
      .getByLabel("Instruction", { exact: true })
      .fill("Reply with one brief greeting.");
    await runDialog
      .getByRole("button", { name: "Submit run", exact: true })
      .click();
    results.push(
      "UI creates persisted agents, immutable versions, enable/disable, run submission and collapsible utility panels",
    );
    await first.page.waitForURL(/\/jobs\/[a-f0-9-]{36}$/);
    const jobId = first.page.url().split("/").at(-1);
    let detail;
    await wait(async () => {
      detail = await api(first.context, `command-center/jobs/${jobId}`);
      if (["FAILED", "CANCELLED"].includes(detail.job.status))
        throw new Error(
          `Actual inference failed: ${JSON.stringify(detail.attempts)}`,
        );
      return detail.job.status === "COMPLETED";
    }, 300000);
    assert.equal(detail.workflow.checkpoint_version, 1);
    assert.ok(detail.output && detail.checkpoints.length === 1);
    assert.equal(
      (await api(second.context, `command-center/jobs/${jobId}`)).job.status,
      "COMPLETED",
    );
    const artifact = await api(
      first.context,
      `workflow/jobs/${jobId}/artifacts/${detail.checkpoints[0].artifact.id}`,
    );
    assert.ok(artifact);
    assert.equal(
      (
        await contributor.context.request.get(
          `${origin}/api/control/command-center/jobs/${jobId}`,
        )
      ).status(),
      404,
    );
    await first.page
      .getByRole("button", { name: "Refresh", exact: true })
      .first()
      .click();
    await first.page.getByText("COMPLETED", { exact: true }).first().waitFor();
    await first.page.screenshot({
      path: path.join(folder, "completed-real-job.png"),
      fullPage: true,
    });
    results.push(
      "real installed local model through actual Windows worker; workflow/checkpoint/artifact/result persisted and shared by explicit membership",
    );
    for (const section of ["agents", "models", "activity"]) {
      await first.page.goto(`${origin}/${section}`);
      await first.page
        .getByRole("button", { name: "Refresh", exact: true })
        .first()
        .waitFor();
      await first.page.locator(".scope-bar select").selectOption(workspace.id);
      if (section === "agents")
        await first.page
          .getByRole("button", {
            name: "Real local model integration",
            exact: true,
          })
          .first()
          .waitFor();
      if (section === "models")
        await first.page
          .getByRole("cell")
          .filter({ hasText: model })
          .first()
          .waitFor();
      if (section === "models") {
        await first.page
          .getByRole("button", { name: "Add model", exact: true })
          .click();
        const installer = first.page.getByRole("dialog", {
          name: "Install a model on an owned worker",
        });
        await installer
          .getByLabel("Owned worker", { exact: true })
          .selectOption(worker.node_id);
        await installer
          .getByLabel("Ollama runtime", { exact: true })
          .selectOption("local");
        assert.equal(await installer.locator('input[type="radio"]').count(), 3);
        await installer.locator('input[value="qwen3:0.6b"]').check();
        await first.page.screenshot({
          path: path.join(folder, "model-selection-installer.png"),
          fullPage: true,
        });
        await installer
          .getByRole("button", { name: "Cancel", exact: true })
          .click();
        results.push(
          "model installer selects owned worker/runtime/catalog without JSON; no model downloaded by this test",
        );
      }
      if (section === "activity")
        await first.page
          .getByText("job.submitted", { exact: true })
          .first()
          .waitFor();
    }
    results.push(
      "agent, installed-model and activity screens render actual scoped APIs",
    );
    const restrictedJob = await api(second.context, "workflow/jobs", {
      workspace_id: workspace.id,
      agent_id: agent.id,
      agent_version: agent.version,
      input: {
        instruction:
          "This remains queued: the node owner has not granted cross-user execution.",
      },
    });
    await wait(async () => {
      const current = await api(second.context, "command-center");
      return (
        new Date(current.generated_at) - new Date(restrictedJob.created_at) >=
        2500
      );
    });
    const restrictedDetail = await api(
      second.context,
      `command-center/jobs/${restrictedJob.id}`,
    );
    assert.equal(restrictedDetail.job.status, "PENDING");
    assert.equal(restrictedDetail.attempts.length, 0);
    await api(second.context, `jobs/${restrictedJob.id}/cancel`, {});
    assert.equal(
      (await api(second.context, `command-center/jobs/${restrictedJob.id}`)).job
        .status,
      "CANCELLED",
    );
    results.push(
      "owner sharing restrictions prevent another administrator's execution; real cancellation persists",
    );
    await api(first.context, `nodes/${worker.node_id}/control`, {
      action: "revoke",
    });
    fs.writeFileSync(path.join(folder, "revoked"), "");
    await wait(
      () => fs.existsSync(path.join(folder, "reconnect-denied")),
      30000,
    );
    const events = await api(first.context, "administration/audit");
    for (const action of [
      "security.login",
      "security.invitation_created",
      "security.invitation_accepted",
      "security.node_credential_created",
      "security.workspace_permission_changed",
    ])
      assert.ok(
        events.some((e) => e.action === action),
        action,
      );
    await first.page.goto(`${origin}/administration`);
    await first.page.getByRole("heading", { name: "Security audit" }).waitFor();
    await first.page
      .getByRole("table", { name: "Durable security events" })
      .waitFor();
    await first.page
      .getByRole("heading", { name: "OIDC test second-sub" })
      .waitFor();
    await first.page.screenshot({
      path: path.join(folder, "administration.png"),
      fullPage: true,
    });
    await first.page.setViewportSize({ width: 390, height: 844 });
    await first.page.evaluate(() => {
      document.documentElement.dataset.theme = "dark";
    });
    assert.equal(
      await first.page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      true,
    );
    await first.page.screenshot({
      path: path.join(folder, "administration-mobile-dark.png"),
      fullPage: true,
    });
    const revoke = await first.context.request.post(
      `${origin}/api/auth/revoke`,
      { headers: { Origin: origin } },
    );
    assert.equal(revoke.status(), 200);
    assert.equal(
      (
        await first.context.request.get(`${origin}/api/control/command-center`)
      ).status(),
      401,
    );
    const logout = await second.context.request.post(
      `${origin}/api/auth/logout`,
      { headers: { Origin: origin } },
    );
    assert.equal(logout.status(), 200);
    assert.equal(
      (
        await second.context.request.get(`${origin}/api/control/command-center`)
      ).status(),
      401,
    );
    results.push(
      "worker credential revocation/reconnect denial, durable security audit, logout and all-session revocation",
    );
    fs.writeFileSync(
      path.join(folder, "browser-result.json"),
      JSON.stringify(
        {
          passed: true,
          google_network: "mocked only in automated test",
          model,
          job_id: jobId,
          results,
        },
        null,
        2,
      ),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
