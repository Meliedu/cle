/**
 * Walk a student through the whole placement sitting, then a CLE decision.
 *
 * Unit and API tests cover the rules; this covers the thing they cannot, which
 * is whether a person can actually get from the intro screen to a released
 * recommendation without the interface getting in their way.
 *
 * Requires a published version: `python scripts/seed_placement_dev.py`.
 * Usage: node scripts/placement-walkthrough.mjs [outDir]
 */

import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = process.argv[2] ?? "tmp/placement-walkthrough";
const CREDS = {
  teacher: { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" },
  student: { email: "meli.student@connect.ust.hk", password: "MeliDemo2026!" },
};

const steps = [];
const problems = [];

function note(step, detail = "") {
  steps.push(`${step}${detail ? ` :: ${detail}` : ""}`);
  console.log(`  ${step}${detail ? ` :: ${detail}` : ""}`);
}

function fail(message) {
  problems.push(message);
  console.log(`  ! ${message}`);
}

async function login(context, role) {
  const page = await context.newPage();
  await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
  await page.waitForSelector('input[type="email"]', { timeout: 30000 });
  await page.fill('input[type="email"]', CREDS[role].email);
  await page.fill('input[type="password"]', CREDS[role].password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/(teacher|student|dashboard)/, { timeout: 30000 });
  await page.waitForTimeout(1200);
  await page.close();
}

async function shot(page, name) {
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
}

async function studentRun(context) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await page.goto(`${BASE}/student/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await shot(page, "01-intro");

  const introText = await page.locator("main").innerText();
  if (!/not an official HSK/i.test(introText)) {
    fail("intro does not state the claim boundary");
  }
  if (!/30 questions/i.test(introText)) fail("intro does not state the item count");
  note("intro rendered");

  await page.getByRole("button", { name: /start the screener/i }).click();
  await page.waitForTimeout(1500);
  await shot(page, "02-eligibility");

  const formMatch = (await page.locator("main").innerText()).match(/Form ([A-E])/);
  note("form allocated", formMatch ? formMatch[1] : "unknown");

  await page.getByRole("button", { name: /i understand, continue/i }).click();
  await page.waitForTimeout(1200);
  // Eligibility and instructions are two transitions behind one button.
  const stillEligibility = await page
    .getByRole("button", { name: /i understand, continue/i })
    .count();
  if (stillEligibility) {
    await page.getByRole("button", { name: /i understand, continue/i }).click();
    await page.waitForTimeout(1200);
  }
  await shot(page, "03-instructions");

  const beginButton = page.getByRole("button", { name: /start the timer and begin/i });
  if ((await beginButton.count()) === 0) {
    fail("never reached the instructions screen");
    await page.close();
    return null;
  }
  if (await beginButton.isEnabled()) {
    fail("the timer can start before the audio check is confirmed");
  }
  await page.getByRole("checkbox").first().check();
  if (!(await beginButton.isEnabled())) {
    fail("confirming audio did not enable the start button");
  }
  note("audio gate works");

  await beginButton.click();
  await page.waitForTimeout(2000);
  await shot(page, "04-sitting-q1");

  const mapButtons = page.locator("nav ul li button");
  await mapButtons.first().waitFor({ timeout: 20000 }).catch(() => {});
  const total = await mapButtons.count();
  if (total !== 30) fail(`question map shows ${total} questions, expected 30`);
  note("sitting started", `${total} questions`);

  // Answer every question by walking the map and picking the first control.
  let answered = 0;
  let sequenceSeen = false;
  for (let i = 0; i < total; i += 1) {
    await mapButtons.nth(i).click();
    await page.waitForTimeout(120);

    const radios = page.locator('main input[type="radio"]');
    const selects = page.locator("main select");
    if ((await selects.count()) >= 3) {
      sequenceSeen = true;
      const options = ["A", "B", "C"];
      for (let s = 0; s < 3; s += 1) {
        await selects.nth(s).selectOption(options[s]);
        await page.waitForTimeout(80);
      }
      answered += 1;
    } else if ((await radios.count()) > 0) {
      await radios.first().check();
      answered += 1;
    } else {
      fail(`question ${i + 1} offered no answer control`);
    }
  }
  if (!sequenceSeen) fail("never encountered the ordering item");
  note("answered every question", `${answered}/${total}`);

  await page.waitForTimeout(1500);
  const progress = await page.locator('[role="progressbar"]').first().getAttribute("aria-valuenow");
  if (progress !== "30") fail(`progress reports ${progress} answered, expected 30`);
  await shot(page, "05-sitting-complete");

  await page.getByRole("button", { name: /review and submit/i }).click();
  await page.waitForTimeout(600);
  await shot(page, "06-confirm");

  const confirmText = await page.locator("main").innerText();
  if (!/cannot change your answers/i.test(confirmText)) {
    fail("submit confirmation does not warn that answers are final");
  }

  await page.getByRole("button", { name: /^submit$/i }).click();
  await page.waitForTimeout(3000);
  await shot(page, "07-pending");

  const pending = await page.locator("main").innerText();
  if (!/with CLE|CLE review/i.test(pending)) fail("no pending-review state after submit");
  for (const leak of ["LANG151", "Band ", "/30", "correct"]) {
    if (pending.includes(leak)) fail(`pending screen leaks result detail: ${leak}`);
  }
  note("pending review shown, no score leaked");

  const url = page.url();
  await page.close();
  if (consoleErrors.length) note("console errors", consoleErrors.slice(0, 2).join(" | "));
  return url;
}

async function teacherRun(context) {
  const page = await context.newPage();
  await page.goto(`${BASE}/teacher/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await shot(page, "08-queue");

  const openLink = page.getByRole("link", { name: /^open$/i }).first();
  if ((await openLink.count()) === 0) {
    fail("submitted attempt did not appear in the review queue");
    await page.close();
    return;
  }
  note("attempt in review queue");

  await openLink.click();
  // Wait for content, not a fixed sleep: the evidence bundle is a wide join and
  // a fixed wait cannot tell "slow" from "broken".
  try {
    await page.getByRole("heading", { name: /placement attempt/i }).waitFor({ timeout: 30000 });
  } catch {
    fail("evidence page never left its loading state");
  }
  await page.waitForTimeout(800);
  await shot(page, "09-evidence");

  const evidence = await page.locator("main").innerText();
  if (!/Answer sheet/i.test(evidence)) fail("evidence bundle has no answer sheet");
  if (!/Reference band profile/i.test(evidence)) fail("evidence bundle has no band profile");
  note("evidence bundle rendered");

  // Approve, then release.
  await page.getByRole("radio", { name: /approve/i }).first().check();
  await page.getByRole("button", { name: /record decision/i }).click();
  await page.waitForTimeout(2500);
  await shot(page, "10-approved");

  await page.getByRole("radio", { name: /release to the student/i }).first().check();
  await page.getByRole("button", { name: /record decision/i }).click();
  await page.waitForTimeout(2500);
  await shot(page, "11-released");

  const after = await page.locator("main").innerText();
  if (!/released/i.test(after)) fail("attempt does not show as released after release");
  note("approved and released");
  await page.close();
}

async function studentResult(context) {
  const page = await context.newPage();
  await page.goto(`${BASE}/student/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(3500);
  await shot(page, "12-result");

  const text = await page.locator("main").innerText();
  if (!/LANG15\d\d/.test(text)) fail("released recommendation not shown to the student");
  if (!/not an official HSK/i.test(text)) fail("released result drops the claim boundary");
  note("student sees the released recommendation");
  await page.close();
}

async function run() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();

  console.log("student:");
  const studentContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await login(studentContext, "student");
  await studentRun(studentContext);

  console.log("teacher:");
  const teacherContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await login(teacherContext, "teacher");
  await teacherRun(teacherContext);

  console.log("student again:");
  await studentResult(studentContext);

  await studentContext.close();
  await teacherContext.close();
  await browser.close();

  writeFileSync(`${OUT}/report.json`, JSON.stringify({ steps, problems }, null, 2));
  console.log(
    problems.length
      ? `\n${problems.length} problem(s) — screenshots in ${OUT}`
      : `\nPASS: full placement walkthrough — screenshots in ${OUT}`
  );
  process.exitCode = problems.length ? 1 : 0;
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
