/**
 * Full-route visual + health sweep.
 *
 * `responsive-audit.mjs` measures layout rules across a representative nine
 * routes. This one is about COVERAGE: it visits every teacher and student
 * route, screenshots each, and records anything that would make a page not
 * production ready:
 *
 *   - the route redirected away (not actually reachable)
 *   - a Next.js error overlay or error boundary rendered
 *   - the page is effectively blank (the `if (!course) return null` class of bug)
 *   - console errors or failed requests
 *   - untranslated raw i18n key paths leaked into the DOM
 *   - raw backend/exception text leaked into the DOM
 *
 * Usage: node scripts/route-sweep.mjs [outDir]
 */

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

if (process.env.NODE_ENV === "production") {
  console.error("refusing to run against a production build");
  process.exit(2);
}

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = process.argv[2] ?? "tmp/route-sweep";
const CREDS = {
  teacher: { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" },
  student: { email: "meli.student@connect.ust.hk", password: "MeliDemo2026!" },
};

/** Static routes. Course-scoped ones are expanded from the live roster. */
const TEACHER_STATIC = [
  ["home", "/teacher/dashboard"],
  ["courses", "/teacher/courses"],
  ["calendar", "/teacher/calendar"],
  ["insights", "/teacher/insights"],
  ["profile", "/teacher/profile"],
  ["notifications", "/teacher/notifications"],
  ["course-new", "/teacher/courses/new"],
];
const TEACHER_COURSE = [
  ["overview", ""],
  ["setup", "/setup"],
  ["sessions", "/sessions"],
  ["sessions-history", "/sessions/history"],
  ["materials", "/materials"],
  ["activities", "/activities"],
  ["practice", "/practice"],
  ["quiz", "/quiz"],
  ["students", "/students"],
  ["enrollment", "/enrollment"],
  ["insights", "/insights"],
  ["reports", "/reports"],
  ["schedule", "/schedule"],
  ["memory", "/memory"],
];
const STUDENT_STATIC = [
  ["home", "/student/dashboard"],
  ["courses", "/student/courses"],
  ["calendar", "/student/calendar"],
  ["progress", "/student/progress"],
  ["join", "/student/join"],
  ["profile", "/student/profile"],
  ["notifications", "/student/notifications"],
];
const STUDENT_COURSE = [
  ["overview", ""],
  ["checkpoints", "/checkpoints"],
  ["materials", "/materials"],
  ["activities", "/activities"],
  ["checklist", "/checklist"],
  ["scores", "/scores"],
  ["reports", "/reports"],
  ["sessions", "/sessions"],
  ["schedule", "/schedule"],
  ["insights", "/insights"],
  ["profile", "/profile"],
];

/** Runs in the page. Returns the defects visible in the rendered DOM. */
const PROBE = `(() => {
  const problems = [];
  const bodyText = document.body.innerText || "";

  // Next.js dev overlay / React error boundary
  if (document.querySelector("nextjs-portal") &&
      /unhandled runtime error|application error/i.test(bodyText)) {
    problems.push({ kind: "error-overlay", detail: bodyText.slice(0, 200) });
  }

  // Effectively blank page: a shell with no meaningful content.
  const main = document.querySelector("main") || document.body;
  const text = (main.innerText || "").trim();
  if (text.length < 20) {
    problems.push({ kind: "blank-page", detail: JSON.stringify(text.slice(0, 60)) });
  }

  // Raw i18n key paths that escaped (next-intl renders these verbatim).
  const keyPath = text.match(/\\b[a-z][a-zA-Z0-9]*(?:\\.[a-z][a-zA-Z0-9_]*){2,}\\b/g) || [];
  const suspects = keyPath.filter((k) => !/\\.(com|org|net|hk|edu|io|js|ts|png|jpg|pdf)$/i.test(k));
  if (suspects.length) {
    problems.push({ kind: "raw-i18n-key", detail: suspects.slice(0, 3).join(", ") });
  }

  // Raw exception / internals leaking into user copy.
  const leak = text.match(/\\b\\w*(?:Error|Exception)\\b\\s*:|Traceback|psycopg|sqlalchemy|asyncpg|\\bNoneType\\b/i);
  if (leak) {
    problems.push({ kind: "raw-error-text", detail: leak[0].slice(0, 80) });
  }

  // A heading is the minimum for an identifiable page.
  if (!document.querySelector("h1, h2")) {
    problems.push({ kind: "no-heading", detail: "" });
  }

  return problems;
})()`;

async function login(context, role) {
  const page = await context.newPage();
  await page.goto(BASE + "/sign-in", { waitUntil: "networkidle" });
  await page.fill('input[type="email"]', CREDS[role].email);
  await page.fill('input[type="password"]', CREDS[role].password);
  await page.click('button[type="submit"]');
  try {
    await page.waitForURL(/\/(teacher|student|dashboard)/, { timeout: 30000 });
  } catch {
    const at = page.url();
    await page.close();
    throw new Error(`login failed for ${role}; still at ${at}`);
  }
  await page.waitForTimeout(1500);
  await page.close();
}

async function firstCourseId(page, role) {
  await page.goto(`${BASE}/${role}/courses`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const href = await page
    .locator(`a[href*="/${role}/courses/"]`)
    .first()
    .getAttribute("href")
    .catch(() => null);
  const m = href && href.match(/courses\/([0-9a-f-]{36})/i);
  return m ? m[1] : null;
}

const findings = [];
let visited = 0;

async function sweep(context, role, routes) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("requestfailed", (r) => {
    const u = r.url();
    if (!/analytics|vitals|_next\/static/.test(u)) {
      consoleErrors.push(`REQFAIL ${u.slice(0, 90)}`);
    }
  });

  for (const [label, url] of routes) {
    consoleErrors.length = 0;
    try {
      await page.goto(BASE + url, { waitUntil: "networkidle", timeout: 45000 });
      await page.waitForTimeout(1100);

      const landed = new URL(page.url()).pathname;
      if (/\/sign-in/.test(landed) && !/sign-in/.test(url)) {
        findings.push({ role, label, url, problems: [{ kind: "not-reachable", detail: `redirected to ${landed}` }] });
        continue;
      }
      visited += 1;

      const problems = await page.evaluate(PROBE);
      if (consoleErrors.length) {
        problems.push({ kind: "console-error", detail: consoleErrors.slice(0, 2).join(" | ").slice(0, 160) });
      }
      if (problems.length) findings.push({ role, label, url, problems });

      await page.screenshot({ path: `${OUT}/${role}-${label}.png`, fullPage: true });
    } catch (e) {
      findings.push({ role, label, url, problems: [{ kind: "load-error", detail: String(e.message).slice(0, 160) }] });
    }
  }
  await page.close();
}

async function run() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();

  for (const role of ["teacher", "student"]) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await login(context, role);

    const probe = await context.newPage();
    const courseId = await firstCourseId(probe, role);
    await probe.close();
    if (!courseId) {
      findings.push({ role, label: "roster", url: `/${role}/courses`, problems: [{ kind: "no-course-found", detail: "cannot expand course-scoped routes" }] });
    }

    const statics = role === "teacher" ? TEACHER_STATIC : STUDENT_STATIC;
    const scoped = role === "teacher" ? TEACHER_COURSE : STUDENT_COURSE;
    const routes = [
      ...statics,
      ...(courseId ? scoped.map(([l, s]) => [`course-${l}`, `/${role}/courses/${courseId}${s}`]) : []),
    ];
    await sweep(context, role, routes);
    await context.close();
  }

  await browser.close();

  writeFileSync(`${OUT}/findings.json`, JSON.stringify(findings, null, 2));
  console.log(`visited ${visited} routes; screenshots in ${OUT}`);
  if (!findings.length) {
    console.log("PASS: no defects across any route.");
    return;
  }
  console.log(`\n${findings.length} route(s) with findings:`);
  for (const f of findings) {
    for (const p of f.problems) {
      console.log(`  [${p.kind}] ${f.role}/${f.label}  ${f.url}  ${p.detail}`);
    }
  }
  process.exitCode = 1;
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
