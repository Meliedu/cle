/**
 * Authenticated smoke check for the placement routes.
 *
 * `curl` cannot distinguish "route exists" from "route missing" here: the proxy
 * redirects every /student and /teacher path to sign-in before routing runs, so
 * a 404 and a real page look identical. This logs in and looks at what actually
 * renders.
 *
 * Usage: node scripts/placement-check.mjs [outDir]
 */

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = process.argv[2] ?? "tmp/placement-check";
const CREDS = {
  teacher: { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" },
  student: { email: "meli.student@connect.ust.hk", password: "MeliDemo2026!" },
};

const ROUTES = [
  ["student", "/student/placement"],
  ["teacher", "/teacher/placement"],
  ["teacher", "/teacher/insights"],
];

async function login(context, role) {
  const page = await context.newPage();
  await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
  await page.fill('input[type="email"]', CREDS[role].email);
  await page.fill('input[type="password"]', CREDS[role].password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(teacher|student|dashboard)/, { timeout: 30000 });
  await page.waitForTimeout(1200);
  await page.close();
}

const findings = [];

async function check(context, role, url) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await page.goto(BASE + url, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(1500);

  const landed = new URL(page.url()).pathname;
  const probe = await page.evaluate(() => {
    const main = document.querySelector("main") || document.body;
    const text = (main.innerText || "").trim();
    return {
      chars: text.length,
      heading: document.querySelector("h1, h2")?.textContent?.trim() ?? null,
      // next-intl renders an unresolved key path verbatim.
      rawKeys: (text.match(/\b[a-z][a-zA-Z0-9]*(?:\.[a-z][a-zA-Z0-9_]*){2,}\b/g) || [])
        .filter((k) => !/\.(com|org|net|hk|edu|io|js|ts|png|jpg|pdf)$/i.test(k))
        .slice(0, 3),
      overlay: Boolean(document.querySelector("nextjs-portal")) &&
        /unhandled runtime error|application error/i.test(document.body.innerText || ""),
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      excerpt: text.slice(0, 220),
    };
  });

  const problems = [];
  if (landed !== url) problems.push(`redirected to ${landed}`);
  if (probe.overlay) problems.push("error overlay rendered");
  if (probe.chars < 20) problems.push(`effectively blank (${probe.chars} chars)`);
  if (!probe.heading) problems.push("no h1/h2 heading");
  if (probe.rawKeys.length) problems.push(`raw i18n key: ${probe.rawKeys.join(", ")}`);
  if (probe.overflow) problems.push("horizontal overflow");
  if (consoleErrors.length) problems.push(`console: ${consoleErrors[0].slice(0, 120)}`);

  await page.screenshot({ path: `${OUT}/${role}${url.replace(/\//g, "-")}.png`, fullPage: true });
  findings.push({ role, url, heading: probe.heading, excerpt: probe.excerpt, problems });
  await page.close();
}

async function run() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();

  for (const role of ["student", "teacher"]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await login(context, role);
    for (const [owner, url] of ROUTES) {
      if (owner !== role) continue;
      await check(context, role, url);
    }
    await context.close();
  }

  await browser.close();
  writeFileSync(`${OUT}/findings.json`, JSON.stringify(findings, null, 2));

  let failed = 0;
  for (const f of findings) {
    const status = f.problems.length ? "FAIL" : "ok";
    if (f.problems.length) failed += 1;
    console.log(`[${status}] ${f.url}`);
    console.log(`       heading: ${f.heading}`);
    console.log(`       text: ${f.excerpt.replace(/\s+/g, " ").slice(0, 150)}`);
    for (const p of f.problems) console.log(`       ! ${p}`);
  }
  console.log(failed ? `\n${failed} route(s) with findings` : "\nPASS: all placement routes render");
  process.exitCode = failed ? 1 : 0;
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
