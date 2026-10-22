// Isolated PostgreSQL / test-only Google provider. No real account or model calls.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);
const origin = "http://127.0.0.1:3010";
const folder = path.resolve(".cache/readiness-ui");

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const errors = [];
  fs.mkdirSync(folder, { recursive: true });
  try {
    async function login(subject) {
      const context = await browser.newContext({
        viewport: { width: 1600, height: 1000 },
      });
      await context.route("https://accounts.google.com/**", async (route) => {
        const url = new URL(route.request().url());
        const callback = new URL(`${origin}/api/auth/callback`);
        callback.searchParams.set("state", url.searchParams.get("state"));
        callback.searchParams.set(
          "code",
          `${subject}|${url.searchParams.get("nonce")}`,
        );
        await route.fulfill({
          status: 302,
          headers: { location: callback.href },
          body: "",
        });
      });
      const page = await context.newPage();
      page.on("pageerror", (e) => errors.push(e.message));
      await page.goto(origin);
      await page.getByRole("button", { name: "Continue with Google" }).click();
      await page
        .getByRole("button", { name: "Sign out", exact: true })
        .waitFor();
      return { context, page };
    }
    const { context, page } = await login("first-sub");
    await page
      .locator("summary")
      .filter({ hasText: /^Create workspace$/ })
      .click();
    await page
      .getByLabel("Workspace name", { exact: true })
      .fill("Readiness workspace");
    await page
      .getByRole("button", { name: "Create workspace", exact: true })
      .click();
    await page.waitForURL(/\/workspaces\/[a-f0-9-]+$/);
    await page
      .getByRole("heading", { name: "Readiness workspace · Overview" })
      .waitFor();
    const workspace = page.url().split("/").at(-1);
    assert.equal(
      new URL(
        await page
          .getByRole("navigation", { name: "Main navigation" })
          .getByRole("link", { name: "Jobs", exact: true })
          .getAttribute("href"),
        origin,
      ).searchParams.get("workspace"),
      workspace,
    );
    await page.goto(`${origin}/workspaces`);
    await page
      .getByRole("link", { name: /Readiness workspace.*Open overview/ })
      .waitFor();
    await page.screenshot({
      path: path.join(folder, "workspaces.png"),
      fullPage: true,
    });
    await page.goto(`${origin}/`);
    await page
      .getByRole("heading", { name: "Worker health and readiness" })
      .waitFor();
    assert.equal(
      await page
        .getByRole("combobox", { name: "Workspace", exact: true })
        .inputValue(),
      "",
    );
    await page.screenshot({
      path: path.join(folder, "overview.png"),
      fullPage: true,
    });

    await page.goto(`${origin}/account`);
    await page
      .getByLabel("Display name", { exact: true })
      .fill("Readiness Owner");
    await page.getByLabel("Location (optional)").fill("Shared location");
    await page.getByRole("button", { name: "Save profile" }).click();
    await page
      .getByRole("status")
      .filter({ hasText: "Profile saved." })
      .waitFor();
    await page.reload();
    assert.equal(
      await page.getByLabel("Display name", { exact: true }).inputValue(),
      "Readiness Owner",
    );
    await page.screenshot({
      path: path.join(folder, "account.png"),
      fullPage: true,
    });

    for (const section of ["images", "analytics"]) {
      await page.goto(`${origin}/${section}`);
      const panel = page.getByRole("complementary", {
        name: "Worker setup and availability",
      });
      await panel
        .getByRole("heading", { name: "Get your worker ready" })
        .waitFor();
      await page
        .getByRole("combobox", { name: "Workspace", exact: true })
        .waitFor();
      const content = page.locator(".workload-layout > section");
      const bounds = await panel.boundingBox(),
        form = await content.boundingBox();
      assert.ok(bounds.x > form.x, "Setup panel should be beside the form");
      await page.screenshot({
        path: path.join(folder, `${section}.png`),
        fullPage: true,
      });
      const toggle = panel.getByRole("button", {
        name: /Worker setup and availability/,
      });
      await toggle.click();
      assert.equal(await toggle.getAttribute("aria-expanded"), "false");
      assert.equal(await page.locator("#readiness-content").isVisible(), false);
      await toggle.click();
      assert.equal(await toggle.getAttribute("aria-expanded"), "true");
      if (section === "images")
        assert.equal(await page.getByLabel("Authorized dataset").count(), 0);
      else
        assert.equal(
          await page.getByRole("option", { name: "Generate images" }).count(),
          0,
        );
    }
    await page.setViewportSize({ width: 760, height: 1000 });
    await page.screenshot({
      path: path.join(folder, "analytics-narrow.png"),
      fullPage: true,
    });
    await context.request
      .post(`${origin}/api/control/administration/invitations`, {
        headers: { Origin: origin },
        data: {
          email: "contributor@example.invalid",
          roles: ["member"],
          hours: 24,
        },
      })
      .then((r) => assert.equal(r.status(), 201));
    const member = await login("contributor-sub");
    await member.page.goto(`${origin}/account`);
    assert.equal(
      await member.page
        .getByRole("link", { name: "Admin settings", exact: true })
        .count(),
      0,
    );
    await member.page.goto(`${origin}/administration`);
    await member.page.waitForURL(`${origin}/account`);
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify({
        status: "passed",
        checks: [
          "OIDC login",
          "workspace creation/directory/scope",
          "global overview",
          "persistent account profile",
          "separate workflows",
          "collapsible side cards",
          "member account/admin guards",
          "no page errors",
        ],
        screenshots: folder,
      }),
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
