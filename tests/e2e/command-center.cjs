// Run through scripts.check_command_center: it owns workers, credentials and cleanup.
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
let playwright;
try {
  playwright = require(process.env.GODFATHER_PLAYWRIGHT_MODULE || "playwright");
} catch {
  playwright = require(path.resolve(".tools/browser/node_modules/playwright"));
}

(async () => {
  const folder = process.argv[2];
  const contextData = JSON.parse(
    fs.readFileSync(path.join(folder, "context.json"), "utf8"),
  );
  const admin = JSON.parse(
    fs.readFileSync(path.join(folder, "admin.json"), "utf8"),
  );
  const browser = await playwright.chromium.launch({
    headless: true,
    ...(process.platform === "win32" ? { channel: "msedge" } : {}),
  });
  const results = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      colorScheme: "dark",
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const unauthorized = await context.request.get(
      "http://127.0.0.1:3000/api/control/command-center",
    );
    assert.equal(unauthorized.status(), 401);
    const csrf = await context.request.post(
      "http://127.0.0.1:3000/api/session",
      {
        headers: { Origin: "https://foreign.invalid" },
        data: { token: "invalid" },
      },
    );
    assert.equal(csrf.status(), 403);
    await page.goto("http://127.0.0.1:3000/");
    await page
      .getByLabel("Administrator credential", { exact: true })
      .fill(admin.token);
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await page.getByRole("button", { name: "Refresh now" }).waitFor();
    assert.equal(
      await page.evaluate(() => localStorage.length + sessionStorage.length),
      0,
    );
    const cookie = (await context.cookies()).find(
      (c) => c.name === "godfather_local_credential",
    );
    assert.ok(cookie?.httpOnly && cookie.sameSite === "Strict");
    await page.getByRole("link", { name: "Nodes", exact: true }).click();
    await page.getByRole("table").waitFor();
    assert.ok((await page.locator("main").innerText()).includes("SIMULATED"));
    for (const node of [contextData.primary_id, contextData.backup_id])
      assert.equal(await page.locator(`a[href="/nodes/${node}"]`).count(), 1);
    await page.getByRole("link", { name: "Jobs", exact: true }).click();
    await page.locator("details.submission > summary").click();
    await page.getByLabel("Agent and pinned version").selectOption({
      label: "Browser recoverable coding-compatible plan · v1",
    });
    await page
      .getByLabel("Instruction", { exact: true })
      .fill("Prepare a portable synthetic coding plan; read-only steps only.");
    await page.getByRole("button", { name: "Submit job", exact: true }).click();
    await page.waitForURL(/\/jobs\/[0-9a-f-]{36}$/);
    const jobId = page.url().split("/").at(-1);
    fs.writeFileSync(
      path.join(folder, "job.json"),
      JSON.stringify({ job_id: jobId }),
    );
    await page.waitForFunction(
      () =>
        document.body.innerText.includes("1 committed steps; checkpoint v1"),
      {},
      { timeout: 90000 },
    );
    assert.ok(
      await page
        .locator(`dd a[href="/nodes/${contextData.primary_id}"]`)
        .count(),
    );
    await page.screenshot({
      path: path.join(folder, "checkpoint-before-failure.png"),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(folder, "stop-primary"),
      "stop owned child process",
    );
    await page.goto(`http://127.0.0.1:3000/nodes/${contextData.primary_id}`);
    await page
      .locator(".state-strip .status-offline")
      .waitFor({ timeout: 90000 });
    await page.screenshot({
      path: path.join(folder, "node-offline.png"),
      fullPage: true,
    });
    await page.goto(`http://127.0.0.1:3000/jobs/${jobId}`);
    await page.waitForFunction(
      () =>
        document.body.innerText.includes("3 committed steps; checkpoint v3"),
      {},
      { timeout: 90000 },
    );
    await page.getByText("Resumed checkpoint v1", { exact: true }).waitFor();
    await page.getByText("job.recovery.assigned", { exact: true }).waitFor();
    assert.equal(
      await page.getByRole("cell", { name: "plan", exact: true }).count(),
      1,
    );
    const api = await context.request.get(
      `http://127.0.0.1:3000/api/control/command-center/jobs/${jobId}`,
    );
    assert.equal(api.status(), 200);
    const detail = await api.json();
    assert.equal(detail.job.status, "COMPLETED");
    assert.deepEqual(
      detail.attempts.map((a) => a.status),
      ["INTERRUPTED", "COMPLETED"],
    );
    assert.equal(detail.attempts[1].node_id, contextData.backup_id);
    assert.equal(
      detail.attempts[1].recovered_from_attempt_id,
      detail.attempts[0].id,
    );
    assert.deepEqual(
      detail.steps.map((s) => s.step_id),
      ["plan", "describe", "summary"],
    );
    await page.screenshot({
      path: path.join(folder, "recovered-job.png"),
      fullPage: true,
    });
    // Check actual model/agent/audit routes and confirmed operational controls.
    await page.goto(`http://127.0.0.1:3000/nodes/${contextData.backup_id}`);
    await page.getByRole("button", { name: "Drain node", exact: true }).click();
    assert.ok(await page.getByRole("dialog").isVisible());
    await page
      .getByRole("button", { name: "Confirm drain node", exact: true })
      .click();
    await page.locator(".state-strip .status-draining").waitFor();
    await page
      .getByRole("button", { name: "Enable node", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Confirm enable node", exact: true })
      .click();
    await page.locator(".state-strip .status-online").waitFor();
    for (const section of ["agents", "models", "activity"]) {
      await page.goto(`http://127.0.0.1:3000/${section}`);
      await page.getByRole("button", { name: "Refresh now" }).waitFor();
      if (section === "models")
        assert.ok(
          (await page.locator("main").innerText()).includes("phase05-fixture"),
        );
      if (section === "agents")
        await page
          .getByRole("button", {
            name: "Browser recoverable coding-compatible plan",
            exact: true,
          })
          .click();
      if (section === "activity") {
        await page.locator('input[name="job_id"]').fill(jobId);
        await page
          .getByRole("button", { name: "Apply filters", exact: true })
          .click();
        await page
          .getByText("job.recovery.assigned", { exact: true })
          .waitFor();
      }
    }
    // Real layouts in both themes and a narrow viewport; no horizontal page overflow.
    for (const [name, viewport, scheme] of [
      ["desktop-light", { width: 1440, height: 1000 }, "light"],
      ["mobile-dark", { width: 390, height: 844 }, "dark"],
    ]) {
      await page.setViewportSize(viewport);
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto("http://127.0.0.1:3000/");
      await page.getByRole("button", { name: "Refresh now" }).waitFor();
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
      );
      await page.screenshot({
        path: path.join(folder, `${name}.png`),
        fullPage: true,
      });
      results.push({ name, noHorizontalOverflow: true });
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(
      path.join(folder, "browser-result.json"),
      JSON.stringify(
        {
          job_id: jobId,
          views: results,
          consoleErrors: errors,
          csrfRejected: true,
          httpOnlyCredential: true,
        },
        null,
        2,
      ),
    );
    await context.close();
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
