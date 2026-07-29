/**
 * Live monitor WebSocket check (CWE-598 fix verification).
 *
 * The teacher live monitor used to carry the JWT in the WS query string, where
 * it lands in proxy and access logs. It now sends the token in the first frame
 * instead. This drives the real UI with a real demo login and proves four
 * things a unit test cannot:
 *
 *   1. the WS URL contains NO token (the security property)
 *   2. the client's first frame is {"type":"auth","token":...}
 *   3. the server answers with a state frame, which it only does AFTER the
 *      token verifies, so this is the end-to-end proof the handshake works
 *   4. an invalid token is rejected with close code 1008 (fail closed)
 *
 * Point 3 matters because the hook sets connected:true optimistically in
 * onopen, before the server has validated anything. A green "connected" badge
 * is therefore NOT evidence that auth succeeded.
 *
 * Usage: node scripts/live-monitor-check.mjs <courseId> <meetingId> <checkpointId>
 */

import { chromium } from "@playwright/test";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const API = process.env.API_URL ?? "http://localhost:8000/api";
const EMAIL = process.env.DEMO_TEACHER ?? "meli.teacher@ust.hk";
const PASSWORD = process.env.DEMO_PASSWORD ?? "MeliDemo2026!";

const [courseId, meetingId, checkpointId, activityId] = process.argv.slice(2);
if (!courseId || !meetingId || !checkpointId) {
  console.error("usage: node scripts/live-monitor-check.mjs <courseId> <meetingId> <checkpointId> [activityId]");
  process.exit(2);
}

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  ${detail}` : ""}`);
}

const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();

const consoleErrors = [];
page.on("console", (m) => {
  if (m.type() === "error") consoleErrors.push(m.text());
});

// Record every WS the page opens, plus its frames in order.
const sockets = [];
page.on("websocket", (ws) => {
  const rec = { url: ws.url(), sent: [], received: [], closed: false };
  sockets.push(rec);
  ws.on("framesent", (f) => rec.sent.push(f.payload));
  ws.on("framereceived", (f) => rec.received.push(f.payload));
  ws.on("close", () => { rec.closed = true; });
});

try {
  // ---- sign in with the demo instructor through the real form ----------------
  await page.goto(`${BASE}/sign-in`, { waitUntil: "domcontentloaded" });
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await Promise.all([
    page.waitForURL((u) => !u.pathname.includes("/sign-in"), { timeout: 30000 }),
    page.click('button[type="submit"]'),
  ]);
  check("demo instructor signs in", true, `-> ${new URL(page.url()).pathname}`);

  // ---- open the checkpoint studio, where the monitor mounts ------------------
  const studio = `${BASE}/teacher/courses/${courseId}/sessions/${meetingId}/checkpoints/${checkpointId}`;
  await page.goto(studio, { waitUntil: "domcontentloaded" });

  // Wait for the monitor socket specifically (the page may open others).
  const deadline = Date.now() + 30000;
  let monitor;
  while (Date.now() < deadline) {
    monitor = sockets.find((s) => s.url.includes(`/checkpoints/${checkpointId}/monitor`));
    if (monitor && monitor.received.length > 0) break;
    await page.waitForTimeout(500);
  }

  if (!monitor) {
    check("monitor WebSocket opened", false, "no socket matching the monitor path");
  } else {
    check("monitor WebSocket opened", true, monitor.url);

    // 1. security property: no credential material anywhere in the URL
    const url = monitor.url;
    const leaks = ["token=", "jwt=", "access_token=", "authorization="].filter((k) =>
      url.toLowerCase().includes(k)
    );
    check(
      "WS URL carries no token (CWE-598)",
      leaks.length === 0 && !/eyJ[A-Za-z0-9_-]{10,}\./.test(url),
      leaks.length ? `leaked: ${leaks.join(",")}` : ""
    );

    // 2. first frame is the auth frame
    let firstOk = false;
    let firstDetail = "no frames sent";
    if (monitor.sent.length > 0) {
      try {
        const first = JSON.parse(monitor.sent[0]);
        firstOk = first.type === "auth" && typeof first.token === "string" && first.token.length > 0;
        firstDetail = `type=${first.type} token=${first.token ? `${first.token.slice(0, 6)}...` : "none"}`;
      } catch {
        firstDetail = "first frame was not JSON";
      }
    }
    check("first client frame is the auth frame", firstOk, firstDetail);

    // 3. THE proof: server replied, which only happens after the token verifies
    const stateFrames = monitor.received
      .map((p) => { try { return JSON.parse(p); } catch { return null; } })
      .filter((m) => m && (m.type === "state" || m.type === "submission" || m.type === "closed"));
    check(
      "server sent a state frame after auth (handshake verified)",
      stateFrames.length > 0,
      stateFrames.length ? `first: ${JSON.stringify(stateFrames[0]).slice(0, 90)}` : "no server frames"
    );
    check("socket stayed open (not policy-closed)", !monitor.closed);
  }

  // ---- monitor UI actually rendered -----------------------------------------
  const live = await page
    .getByText(/live|submission/i)
    .first()
    .isVisible()
    .catch(() => false);
  check("monitor UI rendered", live);

  check("no console errors on the studio page", consoleErrors.length === 0,
    consoleErrors.slice(0, 2).join(" | "));

  // ---- the other changed monitor: activities --------------------------------
  // The activity detail opens from client state on the activities page, not its
  // own route, so we click into it the way an instructor would.
  if (activityId) {
    await page.goto(`${BASE}/teacher/courses/${courseId}/activities`, {
      waitUntil: "domcontentloaded",
    });
    const entry = page.getByRole("button", { name: /vote|greeting/i }).first();
    const link = (await entry.count()) ? entry : page.getByText(/greeting/i).first();
    await link.click({ timeout: 15000 }).catch(() => {});

    const adl = Date.now() + 30000;
    let am;
    while (Date.now() < adl) {
      am = sockets.find((s) => s.url.includes(`/activities/${activityId}/monitor`));
      if (am && am.received.length > 0) break;
      await page.waitForTimeout(500);
    }

    if (!am) {
      check("activity monitor WebSocket opened", false, "no socket matching the activity monitor path");
    } else {
      check("activity monitor WebSocket opened", true);
      check(
        "activity WS URL carries no token",
        !/token=/i.test(am.url) && !/eyJ[A-Za-z0-9_-]{10,}\./.test(am.url)
      );
      let ok = false;
      try {
        const f = JSON.parse(am.sent[0] ?? "{}");
        ok = f.type === "auth" && typeof f.token === "string" && f.token.length > 0;
      } catch { /* leave ok false */ }
      check("activity first frame is the auth frame", ok);
      check(
        "activity server sent a frame after auth",
        am.received.length > 0,
        am.received.length ? `first: ${String(am.received[0]).slice(0, 80)}` : ""
      );
    }
  }

  // ---- negative: a bad token must be rejected with 1008 ----------------------
  const wsBase = API.replace(/^http/, "ws");
  const negative = await page.evaluate(
    ([wsUrl]) =>
      new Promise((resolve) => {
        const ws = new WebSocket(wsUrl);
        const t = setTimeout(() => resolve({ code: -1, note: "timeout" }), 10000);
        ws.onopen = () => ws.send(JSON.stringify({ type: "auth", token: "not-a-valid-jwt" }));
        ws.onclose = (e) => { clearTimeout(t); resolve({ code: e.code }); };
        ws.onmessage = (e) => { clearTimeout(t); resolve({ code: 0, note: `got data: ${e.data}` }); };
      }),
    [`${wsBase}/checkpoints/${checkpointId}/monitor`]
  );
  check("invalid token closed with 1008", negative.code === 1008,
    `close code ${negative.code}${negative.note ? ` (${negative.note})` : ""}`);

  // ---- negative: no auth frame at all must also be rejected ------------------
  const silent = await page.evaluate(
    ([wsUrl]) =>
      new Promise((resolve) => {
        const ws = new WebSocket(wsUrl);
        const t = setTimeout(() => resolve({ code: -1, note: "still open after 15s" }), 15000);
        ws.onclose = (e) => { clearTimeout(t); resolve({ code: e.code }); };
        ws.onmessage = (e) => { clearTimeout(t); resolve({ code: 0, note: `got data: ${e.data}` }); };
      }),
    [`${wsBase}/checkpoints/${checkpointId}/monitor`]
  );
  check("silent client closed with 1008 after timeout", silent.code === 1008,
    `close code ${silent.code}${silent.note ? ` (${silent.note})` : ""}`);
} catch (err) {
  check("harness completed", false, String(err).slice(0, 200));
} finally {
  await page.screenshot({ path: "tmp/live-monitor.png", fullPage: true }).catch(() => {});
  await browser.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
process.exit(failed.length === 0 ? 0 : 1);
