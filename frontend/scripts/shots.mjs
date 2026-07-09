// Dev visual-QA harness. Logs in as a demo role via the real sign-in form,
// then screenshots a list of routes (desktop + mobile). Used to iterate on the
// UI/UX polish and to smoke-test the full auth + role-routing + data flow.
//
// Usage:
//   node scripts/shots.mjs smoke              # login as teacher + student, report landing
//   node scripts/shots.mjs <role> <out> <url> [url...]   # capture routes for a role
// role ∈ teacher | student | public
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

// Dev-only visual-QA harness. Refuse to run under a production environment so it
// can never be wired into a deployed context (mirrors scripts/seed-auth.mjs).
if (process.env.NODE_ENV === "production") {
  console.error("Refusing to run the screenshot harness with NODE_ENV=production.");
  process.exit(1);
}

const BASE = "http://localhost:3000";
const CREDS = {
  teacher: { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" },
  student: { email: "meli.student@connect.ust.hk", password: "MeliDemo2026!" },
};

async function login(context, role) {
  const page = await context.newPage();
  await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', CREDS[role].email);
  await page.fill('input[name="password"]', CREDS[role].password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(teacher|student|dashboard)/, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const landed = page.url();
  await page.close();
  return landed;
}

async function smoke() {
  const browser = await chromium.launch();
  for (const role of ["teacher", "student"]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    try {
      const landed = await login(context, role);
      console.log(`${role}: landed at ${landed}`);
    } catch (e) {
      console.log(`${role}: LOGIN FAILED — ${e.message}`);
    }
    await context.close();
  }
  await browser.close();
}

async function capture(role, outDir, urls) {
  await mkdir(outDir, { recursive: true });
  const browser = await chromium.launch();
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  if (role !== "public") {
    const landed = await login(desktop, role);
    console.log(`[auth] ${role} -> ${landed}`);
  }
  for (const url of urls) {
    const slug = url.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "root";
    const page = await desktop.newPage();
    try {
      await page.goto(`${BASE}${url}`, { waitUntil: "networkidle", timeout: 25000 });
      await page.waitForTimeout(1200);
      await page.screenshot({ path: `${outDir}/${slug}.png`, fullPage: true });
      console.log(`shot ${url} -> ${slug}.png`);
    } catch (e) {
      console.log(`FAIL ${url}: ${e.message}`);
    }
    await page.close();
  }
  await desktop.close();
  await browser.close();
}

const [mode, ...rest] = process.argv.slice(2);
if (mode === "smoke") {
  await smoke();
} else {
  const [role, outDir, ...urls] = [mode, ...rest];
  await capture(role, outDir, urls);
}
