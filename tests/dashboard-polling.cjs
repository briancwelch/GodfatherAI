// Uses the existing TypeScript loader in dashboard-components.cjs and Node fake timers.
const assert = require("node:assert/strict");
const { getEventListeners } = require("node:events");
const test = require("node:test");

const flush = () => new Promise(setImmediate);
const json = (value, status = 200) => Response.json(value, { status });

function fixture(context, fetch) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const window = Object.assign(new EventTarget(), {
    location: { reload: context.mock.fn() },
  });
  const document = Object.assign(new EventTarget(), {
    visibilityState: "visible",
  });
  globalThis.window = window;
  globalThis.document = document;
  context.mock.timers.enable({ apis: ["setTimeout"] });
  context.mock.method(globalThis, "fetch", fetch);
  for (const name of ["control-client", "polling"])
    delete require.cache[
      require.resolve(`../apps/dashboard/src/lib/${name}.ts`)
    ];
  const client = require("../apps/dashboard/src/lib/control-client.ts");
  const polling = require("../apps/dashboard/src/lib/polling.ts");
  const stops = [];
  context.after(() => {
    stops.forEach((stop) => stop());
    require("../apps/dashboard/src/lib/notifications.ts").clearNotifications();
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  });
  return {
    client,
    window,
    document,
    start(options = {}) {
      const stop = polling.startPolling({
        request: (signal) =>
          client.control("command-center", undefined, undefined, signal),
        onData: () => {},
        onError: () => {},
        ...options,
      });
      stops.push(stop);
      return stop;
    },
    async tick(ms) {
      context.mock.timers.tick(ms);
      await flush();
    },
  };
}

test("a 401 pauses every protected poller and prevents requests from new scopes or mutations", async (context) => {
  let status = 200;
  const calls = [];
  const errors = [];
  const f = fixture(context, async (url) => {
    calls.push(url);
    return json({}, status);
  });
  f.start({ onError: (error) => errors.push(error.status) });
  f.start({
    request: (signal) =>
      f.client.control("appearance", undefined, undefined, signal),
  });
  await flush();
  status = 401;
  await f.tick(3000);
  assert.equal(f.client.authenticationRequired(), true);
  assert.ok(errors.includes(401));
  const stoppedAt = calls.length;
  f.start({ request: () => f.client.control("command-center/jobs/new-scope") });
  await assert.rejects(
    f.client.control("jobs", { instruction: "never replay" }),
    { status: 401 },
  );
  await f.tick(600000);
  assert.equal(calls.length, stoppedAt);
});

test("identity is checked on mount and focus without a recurring auth timer", async (context) => {
  let calls = 0;
  const f = fixture(context, async () => {
    calls += 1;
    return json({ id: "owner" });
  });
  f.start({
    intervalMs: null,
    sessionCheck: true,
    request: () => f.client.verifySession(),
  });
  await flush();
  assert.equal(calls, 1);
  await f.tick(600000);
  assert.equal(calls, 1);
  f.window.dispatchEvent(new Event("focus"));
  await flush();
  assert.equal(calls, 2);
});

for (const failedProbe of [401, 503]) {
  test(`focus verifies the session once, remains paused on ${failedProbe}, then resumes after sign-in`, async (context) => {
    let signedIn = false;
    let probeStatus = failedProbe;
    const calls = [];
    const f = fixture(context, async (url) => {
      calls.push(url);
      if (url.endsWith("auth/me")) return json({ id: "owner" }, probeStatus);
      return json({ value: "fresh" }, signedIn ? 200 : 401);
    });
    const values = [];
    f.start({ onData: (value) => values.push(value) });
    await flush();
    f.start();
    f.window.dispatchEvent(new Event("focus"));
    f.document.dispatchEvent(new Event("visibilitychange"));
    await flush();
    assert.equal(calls.filter((url) => url.endsWith("auth/me")).length, 1);
    assert.equal(f.client.authenticationRequired(), true);
    const pausedAt = calls.length;
    await f.tick(600000);
    assert.equal(calls.length, pausedAt);
    signedIn = true;
    probeStatus = 200;
    f.window.dispatchEvent(new Event("focus"));
    await flush();
    assert.equal(f.client.authenticationRequired(), false);
    assert.equal(calls.filter((url) => url.endsWith("auth/me")).length, 2);
    assert.deepEqual(values, [{ value: "fresh" }]);
    const resumedAt = calls.length;
    await f.tick(3000);
    assert.equal(calls.length, resumedAt + 2);
  });
}

for (const intervalMs of [3000, null]) {
  test(`explicit session verification resumes ${intervalMs === null ? "initial reads" : "polling"} without a focus event`, async (context) => {
    let signedIn = false;
    const values = [];
    const f = fixture(context, async (url) =>
      json(
        url.endsWith("auth/me") ? { id: "owner" } : { value: "fresh" },
        signedIn ? 200 : 401,
      ),
    );
    f.start({ intervalMs, onData: (value) => values.push(value) });
    await flush();
    signedIn = true;
    await f.client.verifySession();
    await flush();
    assert.deepEqual(values, [{ value: "fresh" }]);
  });
}

for (const failure of ["http", "network"]) {
  test(`${failure} failures back off to 60 seconds and success restores the normal interval`, async (context) => {
    let healthy = false;
    let calls = 0;
    const f = fixture(context, async () => {
      calls += 1;
      if (!healthy && failure === "network") throw new TypeError("offline");
      return json({}, healthy ? 200 : 503);
    });
    f.start();
    await flush();
    assert.equal(calls, 1);
    for (const delay of [6000, 12000, 24000, 48000, 60000, 60000]) {
      const before = calls;
      await f.tick(delay - 1);
      assert.equal(calls, before);
      await f.tick(1);
      assert.equal(calls, before + 1);
    }
    healthy = true;
    await f.tick(60000);
    const recoveredAt = calls;
    await f.tick(2999);
    assert.equal(calls, recoveredAt);
    await f.tick(1);
    assert.equal(calls, recoveredAt + 1);
  });
}

test("effect cleanup aborts in-flight work, removes listeners and ignores late results", async (context) => {
  let resolve;
  let signal;
  let calls = 0;
  const values = [];
  const errors = [];
  const f = fixture(context, (url, init) => {
    if (url.endsWith("auth/me")) return Promise.resolve(json({ id: "owner" }));
    calls += 1;
    signal = init.signal;
    return new Promise((done) => {
      resolve = done;
    });
  });
  const stop = f.start({
    onData: (value) => values.push(value),
    onError: (error) => errors.push(error),
  });
  await f.tick(60000);
  f.window.dispatchEvent(new Event("focus"));
  assert.equal(calls, 1, "slow requests must not overlap");
  stop();
  assert.equal(signal.aborted, true);
  assert.equal(getEventListeners(f.window, "focus").length, 0);
  assert.equal(getEventListeners(f.document, "visibilitychange").length, 0);
  resolve(json({ private: "late" }));
  await flush();
  await f.tick(600000);
  assert.deepEqual(values, []);
  assert.deepEqual(errors, []);
  assert.equal(calls, 1);
});

test("effect cleanup cancels scheduled backoff and future focus retries", async (context) => {
  let calls = 0;
  const f = fixture(context, async () => {
    calls += 1;
    return json({}, 503);
  });
  const stop = f.start();
  await flush();
  stop();
  await f.tick(600000);
  f.window.dispatchEvent(new Event("focus"));
  await flush();
  assert.equal(calls, 1);
});

test("hidden pages stop requests until they become visible", async (context) => {
  let calls = 0;
  const f = fixture(context, async (url) => {
    if (url.endsWith("auth/me")) return json({ id: "owner" });
    calls += 1;
    return json({});
  });
  f.document.visibilityState = "hidden";
  f.start();
  await f.tick(600000);
  assert.equal(calls, 0);
  f.document.visibilityState = "visible";
  f.document.dispatchEvent(new Event("visibilitychange"));
  await flush();
  assert.equal(calls, 1);
  f.document.visibilityState = "hidden";
  await f.tick(600000);
  assert.equal(calls, 1);
  f.document.visibilityState = "visible";
  f.window.dispatchEvent(new Event("focus"));
  await flush();
  assert.equal(calls, 2);
});

test("an older successful identity response cannot undo a newer 401", async (context) => {
  let resolve;
  const f = fixture(context, async (url) => {
    if (url.endsWith("auth/me"))
      return new Promise((done) => {
        resolve = done;
      });
    return json({}, 401);
  });
  const verifying = f.client.verifySession();
  await assert.rejects(f.client.control("command-center"), { status: 401 });
  resolve(json({ id: "owner" }));
  await assert.rejects(verifying, { status: 401 });
  assert.equal(f.client.authenticationRequired(), true);
});

test("another account triggers a clean reload without resuming the previous account's polls", async (context) => {
  const calls = [];
  const f = fixture(context, async (url) => {
    calls.push(url);
    return json({ id: "another-owner" }, url.endsWith("auth/me") ? 200 : 401);
  });
  f.client.rememberSessionOwner("original-owner");
  f.start();
  await flush();
  await assert.rejects(f.client.verifySession(), { status: 401 });
  assert.equal(f.window.location.reload.mock.callCount(), 1);
  assert.equal(f.client.authenticationRequired(), true);
  await f.tick(600000);
  assert.deepEqual(calls, [
    "/api/control/command-center",
    "/api/control/auth/me",
  ]);
});

test("unmounting the last poller cancels shared session verification", async (context) => {
  let signal;
  let resolve;
  const f = fixture(context, async (url, init) => {
    if (url.endsWith("auth/me")) {
      signal = init.signal;
      return new Promise((done) => {
        resolve = done;
      });
    }
    return json({}, 401);
  });
  const stop = f.start();
  await flush();
  f.window.dispatchEvent(new Event("focus"));
  stop();
  assert.equal(signal.aborted, true);
  resolve(json({ id: "owner" }));
  await flush();
  assert.equal(f.client.authenticationRequired(), true);
});

test("a workspace 403 does not expire the entire authenticated session", async (context) => {
  let calls = 0;
  const f = fixture(context, async () => {
    calls += 1;
    return json({}, 403);
  });
  f.start();
  await flush();
  assert.equal(f.client.authenticationRequired(), false);
  await f.tick(6000);
  assert.equal(calls, 2);
});

test("a failed batch aborts remaining requests before its backoff retry", async (context) => {
  let signal;
  let calls = 0;
  const f = fixture(context, async (url, init) => {
    calls += 1;
    if (url.endsWith("appearance")) {
      signal = init.signal;
      return new Promise((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), {
          once: true,
        });
      });
    }
    return json({}, 503);
  });
  f.start({
    request: (signal) =>
      Promise.all([
        f.client.control("command-center", undefined, undefined, signal),
        f.client.control("appearance", undefined, undefined, signal),
      ]),
  });
  await flush();
  assert.equal(signal.aborted, true);
  assert.equal(calls, 2);
  await f.tick(5999);
  assert.equal(calls, 2);
  await f.tick(1);
  assert.equal(calls, 4);
});

test("a late 401 after effect cleanup cannot expire a newer view", async (context) => {
  let resolve;
  const f = fixture(
    context,
    async () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  const stop = f.start();
  stop();
  resolve(json({}, 401));
  await flush();
  assert.equal(f.client.authenticationRequired(), false);
});
