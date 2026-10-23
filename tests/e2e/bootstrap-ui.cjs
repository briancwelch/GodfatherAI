// Run only against tests.e2e.auth_server and its disposable godfather_test database.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(
  path.resolve(".tools/browser/node_modules/playwright"),
);
const origin = "http://127.0.0.1:3010";
const folder = path.resolve(".cache/bootstrap-ui");

(async () => {
  fs.mkdirSync(folder, { recursive: true });
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  const errors = [];
  try {
    const context = await browser.newContext({
      viewport: { width: 1600, height: 1100 },
    });
    await context.route("https://accounts.google.com/**", async (route) => {
      const request = new URL(route.request().url());
      const callback = new URL(`${origin}/api/auth/callback`);
      callback.searchParams.set("state", request.searchParams.get("state"));
      callback.searchParams.set(
        "code",
        `first-sub|${request.searchParams.get("nonce")}`,
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
    await page.getByRole("button", { name: "Sign out", exact: true }).waitFor();
    await page
      .locator(".environment-label")
      .filter({ hasText: /test environment/i })
      .waitFor();
    // Only the isolated test server has this environment label and bootstrap user.
    assert.match(
      await page.locator(".environment-label").innerText(),
      /test environment/i,
    );
    const created = await context.request.post(
      `${origin}/api/control/administration/workspaces`,
      {
        headers: { Origin: origin },
        data: { name: "Bootstrap browser fixture" },
      },
    );
    assert.equal(created.status(), 201, await created.text());
    const scanned = [];
    for (const theme of ["light", "dark"]) {
      await page
        .getByRole("combobox", { name: "Theme", exact: true })
        .selectOption(theme);
      for (const route of [
        "/",
        "/workspaces",
        "/jobs",
        "/nodes",
        "/agents",
        "/models",
        "/providers",
        "/images",
        "/analytics",
        "/distributed",
        "/distributed-tasks",
        "/activity",
        "/account",
        "/administration",
        "/administration/appearance",
      ]) {
        const response = await page.goto(origin + route);
        assert.equal(response.status(), 200, route);
        await page
          .getByRole("button", { name: "Sign out", exact: true })
          .waitFor();
        await page.waitForFunction(
          () =>
            document.documentElement.dataset.bsTheme ===
            document.documentElement.dataset.theme,
        );
        if (route === "/account")
          await page.getByLabel("Display name", { exact: true }).waitFor();
        else
          await page
            .locator(".environment-label")
            .filter({ hasText: /test environment/i })
            .waitFor();
        const text = await page.locator("body").innerText();
        assert.doesNotMatch(
          text,
          /\u00c2[\u0080-\u00bf]|\u00e2[\u0080-\u00bf\u20ac\u2020]|\ufffd/u,
          route,
        );
        assert.ok(
          await page.locator(".btn").count(),
          route + " Bootstrap buttons",
        );
        assert.equal(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          true,
          route + " horizontal overflow",
        );
        scanned.push(`${theme}:${route}`);
      }
    }
    await page
      .getByRole("combobox", { name: "Theme", exact: true })
      .selectOption("light");
    await page.goto(`${origin}/administration/appearance`);
    await page
      .getByLabel("Button style", { exact: true })
      .selectOption("outline");
    await page.getByLabel("Panel padding (px)").fill("24");
    await page.getByLabel("Progress bar height (px)").fill("18");
    await page
      .getByLabel("Toast position", { exact: true })
      .selectOption("top-start");
    await page.getByLabel("Toast width (px)").fill("420");
    const preview = page.getByRole("region", { name: "Appearance preview" });
    const progress = preview.getByRole("progressbar");
    assert.equal(await progress.getAttribute("aria-valuenow"), "65");
    assert.equal(
      await progress.evaluate((el) => getComputedStyle(el).height),
      "18px",
    );
    await page.getByRole("button", { name: "Save site appearance" }).click();
    await page
      .getByRole("status")
      .filter({ hasText: "Site appearance saved" })
      .first()
      .waitFor();
    await page.reload();
    assert.equal(
      await page.getByLabel("Button style", { exact: true }).inputValue(),
      "outline",
    );
    assert.equal(
      await page.getByLabel("Progress bar height (px)").inputValue(),
      "18",
    );
    await page.screenshot({
      path: path.join(folder, "admin-appearance.png"),
      fullPage: true,
    });

    // Explicit synthetic worker fixture: render capabilities without running inference.
    await context.route("**/api/control/workloads/options?*", (route) =>
      route.fulfill({
        json: {
          nodes: [
            {
              id: "fixture-a",
              name: "Chromium",
              available: true,
              analytics: true,
              image_models: [],
            },
            {
              id: "fixture-b",
              name: "Carbon",
              available: true,
              analytics: true,
              image_models: [
                "Local-XL-model-with-a-long-name-to-check-wrapping",
              ],
            },
            {
              id: "fixture-c",
              name: "Radium",
              available: false,
              analytics: false,
              image_models: ["Installed offline model"],
            },
          ],
          sql_note: "Synthetic browser test fixture; no worker execution.",
        },
      }),
    );
    await page.goto(`${origin}/images`);
    const readiness = page.getByRole("complementary", {
      name: "Worker setup and availability",
    });
    await readiness
      .getByText(
        "Image model: Local-XL-model-with-a-long-name-to-check-wrapping",
        { exact: true },
      )
      .waitFor();
    assert.equal(await readiness.locator(".status-online").count(), 2);
    assert.equal(await readiness.locator(".status-unavailable").count(), 1);
    const link = readiness.getByRole("link", {
      name: "Connect or inspect a worker",
    });
    assert.ok((await link.boundingBox()).height >= 42);
    await page.screenshot({
      path: path.join(folder, "images-desktop.png"),
      fullPage: true,
    });
    const toggle = readiness.getByRole("button", {
      name: "Worker setup and availability",
    });
    await toggle.click();
    assert.equal(await page.locator("#readiness-content").isVisible(), false);
    await toggle.click();
    await page.goto(`${origin}/analytics`);
    await page
      .getByLabel("Analysis request / report context")
      .fill("Client validation fixture");
    await page.getByLabel("Authorized dataset").setInputFiles({
      name: "invalid.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("fixture"),
    });
    await page.getByLabel(/I authorize processing/).check();
    await page
      .getByRole("button", { name: "Run workload", exact: true })
      .click();
    const errorToast = page.locator(".toast-container .toast-error");
    await errorToast.waitFor();
    assert.match(await errorToast.innerText(), /Choose a CSV, JSON or XLSX/);
    const toastPosition = await page.locator(".toast-container").boundingBox();
    assert.ok(
      toastPosition.x < 30 && toastPosition.y < 30,
      "Saved toast corner applies",
    );
    await page.screenshot({
      path: path.join(folder, "warning-toast.png"),
      fullPage: true,
    });
    await errorToast.getByRole("button", { name: /Dismiss/ }).click();
    assert.equal(await errorToast.count(), 0);
    for (const width of [760, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const route of [
        "/images",
        "/jobs",
        "/account",
        "/administration/appearance",
      ]) {
        await page.goto(origin + route);
        await page
          .getByRole("button", { name: "Sign out", exact: true })
          .waitFor();
        if (route === "/account")
          await page.getByLabel("Display name", { exact: true }).waitFor();
        else
          await page
            .locator(".environment-label")
            .filter({ hasText: /test environment/i })
            .waitFor();
        if (route === "/images")
          await page.locator(".worker-availability-row").first().waitFor();
        if (route === "/administration/appearance")
          await page.locator(".bootstrap-settings").waitFor();
        if (route === "/account")
          await page.getByLabel("Display name", { exact: true }).waitFor();
        assert.equal(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          true,
          `${width}:${route} overflow`,
        );
        await page.screenshot({
          path: path.join(
            folder,
            `${width}-${route.slice(1).replaceAll("/", "-")}.png`,
          ),
          fullPage: true,
        });
      }
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`${origin}/administration/appearance`);
    await page.getByRole("progressbar").waitFor();
    assert.equal(
      await page
        .locator(".progress-bar")
        .first()
        .evaluate((el) => getComputedStyle(el).animationName),
      "none",
    );
    assert.deepEqual(errors, []);
    console.log(
      JSON.stringify(
        {
          status: "passed",
          browser: await browser.version(),
          scanned,
          checks: [
            "saved Bootstrap settings",
            "measured progress",
            "worker badges",
            "collapse",
            "persistent error toast and dismissal",
            "tablet/mobile overflow",
            "reduced motion",
          ],
          screenshots: folder,
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
