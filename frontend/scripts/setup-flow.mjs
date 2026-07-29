// Drives the real course-setup flow as the demo teacher and reports what breaks.
//
// Captures, per step: the URL, the visible stage, console errors, failed
// network requests, and a screenshot. Written to be run against a local dev
// stack while iterating on the five-stage setup rebuild.
//
// Usage: node scripts/setup-flow.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdir } from "node:fs/promises";

if (process.env.NODE_ENV === "production") {
  console.error("Refusing to run the flow harness with NODE_ENV=production.");
  process.exit(1);
}

const BASE = "http://localhost:3000";
const TEACHER = { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" };

const consoleErrors = [];
const netFailures = [];
const pageErrors = [];

function wire(page) {
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text().slice(0, 300));
  });
  page.on("pageerror", (err) => pageErrors.push(String(err).slice(0, 400)));
  page.on("response", (res) => {
    if (res.status() >= 400) {
      netFailures.push(`${res.status()} ${res.request().method()} ${res.url()}`);
    }
  });
}

function drain(label) {
  const out = [];
  if (pageErrors.length) out.push(`  PAGE ERRORS:\n    ${pageErrors.join("\n    ")}`);
  if (consoleErrors.length)
    out.push(`  CONSOLE:\n    ${[...new Set(consoleErrors)].join("\n    ")}`);
  if (netFailures.length)
    out.push(`  NETWORK:\n    ${[...new Set(netFailures)].join("\n    ")}`);
  pageErrors.length = 0;
  consoleErrors.length = 0;
  netFailures.length = 0;
  if (out.length) {
    console.log(`\n[${label}]`);
    console.log(out.join("\n"));
  }
  return out.length > 0;
}

async function snapshot(page, outDir, name) {
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: true });
  return page.evaluate(() => {
    const h1 = document.querySelector("h1");
    const stepper = document.querySelector('nav[aria-label="Course setup stages"]');
    const stages = stepper
      ? [...stepper.querySelectorAll("button")].map((b) => ({
          label: (b.textContent || "").replace(/\s+/g, " ").trim(),
          disabled: b.hasAttribute("disabled"),
          current: b.getAttribute("aria-current") === "step",
        }))
      : null;
    const body = (document.body.innerText || "").slice(0, 400);
    return {
      url: location.pathname + location.search,
      h1: h1 ? h1.textContent.trim() : null,
      stages,
      bodyHead: body.replace(/\s+/g, " ").slice(0, 240),
    };
  });
}

async function run() {
  const outDir = process.argv[2] || "setup-out";
  await mkdir(outDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();
  wire(page);

  // ---- sign in -----------------------------------------------------------
  await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', TEACHER.email);
  await page.fill('input[name="password"]', TEACHER.password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/teacher/, { timeout: 25000 }).catch(() => {});
  await page.waitForTimeout(2000);
  console.log("signed in ->", page.url());
  drain("sign-in");

  // ---- roster ------------------------------------------------------------
  await page.goto(`${BASE}/teacher/courses`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  const roster = await snapshot(page, outDir, "01-roster");
  console.log("\n[roster]", JSON.stringify(roster, null, 2).slice(0, 900));
  drain("roster");

  // Prefer a course that is still in setup, since that is the flow under test.
  const setupHref = await page.evaluate(() => {
    const links = [...document.querySelectorAll('a[href*="/setup"]')];
    return links.length ? links[0].getAttribute("href") : null;
  });
  const anyCourse = await page.evaluate(() => {
    const link = document.querySelector('a[href^="/teacher/courses/"]');
    return link ? link.getAttribute("href") : null;
  });
  console.log("\nsetup link on roster:", setupHref);
  console.log("first course link:", anyCourse);

  let target = setupHref;
  if (!target && anyCourse) {
    const base = anyCourse.split("?")[0];
    target = `${base}/setup`;
  }
  if (!target) {
    console.log("NO COURSE FOUND on roster; cannot walk setup.");
    await browser.close();
    return;
  }

  // ---- setup: landing ----------------------------------------------------
  const setupUrl = target.startsWith("http") ? target : `${BASE}${target}`;
  await page.goto(setupUrl, { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);
  const landing = await snapshot(page, outDir, "02-setup-landing");
  console.log("\n[setup landing]", JSON.stringify(landing, null, 2).slice(0, 1400));
  const brokeOnLanding = drain("setup landing");

  // ---- walk every stage --------------------------------------------------
  for (const stage of ["basics", "sources", "schedule", "review", "publish"]) {
    const url = `${setupUrl.split("?")[0]}?stage=${stage}`;
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForTimeout(2200);
    const snap = await snapshot(page, outDir, `03-stage-${stage}`);
    console.log(`\n[stage ${stage}] url=${snap.url} h1=${snap.h1}`);
    console.log(`  body: ${snap.bodyHead}`);
    if (snap.stages) {
      console.log(
        "  stepper: " +
          snap.stages
            .map(
              (s) =>
                `${s.label.replace(/\s+/g, "")}${s.current ? "*" : ""}${s.disabled ? "(locked)" : ""}`
            )
            .join(" | ")
      );
    } else {
      console.log("  stepper: MISSING");
    }
    drain(`stage ${stage}`);
  }

  await browser.close();
  if (brokeOnLanding) process.exitCode = 1;
}

run().catch((e) => {
  console.error("HARNESS ERROR:", e);
  process.exit(1);
});
