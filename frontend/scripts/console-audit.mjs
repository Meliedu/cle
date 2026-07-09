// Dev-only: log browser console errors/warnings + failed requests across a set
// of authenticated routes, per role. Surfaces hydration mismatches, React key
// warnings, failed fetches, and uncaught errors that the Next.js dev overlay
// counts as "Issues". Refuses to run under production.
//
//   node scripts/console-audit.mjs teacher /teacher/dashboard /teacher/courses ...
//   node scripts/console-audit.mjs student /student/dashboard ...
import { chromium } from "playwright";

if (process.env.NODE_ENV === "production") {
  console.error("Refusing to run the console audit with NODE_ENV=production.");
  process.exit(1);
}

const BASE = "http://localhost:3000";

// Third-party telemetry that self-loads (e.g. Vercel Analytics' dev debug
// script). These are not app defects — they load fine from their own origin in
// production and only fail here because the headless sandbox blocks the opaque
// cross-origin response. Scope the audit to real app-level issues.
const THIRD_PARTY_NOISE = [/va\.vercel-scripts\.com/, /vitals\.vercel-insights\.com/];
const isNoise = (url) => THIRD_PARTY_NOISE.some((re) => re.test(url));
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
  await page.waitForTimeout(1200);
  await page.close();
}

const [role, ...urls] = process.argv.slice(2);
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
if (role !== "public") await login(ctx, role);

let total = 0;
for (const url of urls) {
  const page = await ctx.newPage();
  const msgs = [];
  page.on("console", (m) => {
    if (m.type() === "error" || m.type() === "warning") msgs.push(`[${m.type()}] ${m.text()}`);
  });
  page.on("pageerror", (e) => msgs.push(`[pageerror] ${e.message}`));
  page.on("requestfailed", (r) => {
    const f = r.failure();
    // Ignore benign aborted navigations + self-loading third-party telemetry.
    if (f && !/ERR_ABORTED/.test(f.errorText) && !isNoise(r.url()))
      msgs.push(`[reqfail] ${r.url()} — ${f.errorText}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !isNoise(r.url())) msgs.push(`[http ${r.status()}] ${r.url()}`);
  });
  try {
    await page.goto(`${BASE}${url}`, { waitUntil: "networkidle", timeout: 25000 });
    await page.waitForTimeout(1500);
  } catch (e) {
    msgs.push(`[navfail] ${e.message}`);
  }
  const uniq = [...new Set(msgs)];
  total += uniq.length;
  console.log(`\n=== ${url} (${uniq.length}) ===`);
  for (const m of uniq) console.log("  " + m);
  await page.close();
}
console.log(`\nTOTAL ISSUES: ${total}`);
await browser.close();
