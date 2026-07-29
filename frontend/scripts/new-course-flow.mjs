// Drives "Create course" -> setup as the demo teacher, which is the entry
// point a real instructor uses. Reports where it breaks.
//
// Usage: node scripts/new-course-flow.mjs [outDir]
import { chromium } from "playwright";
import { mkdir } from "node:fs/promises";

if (process.env.NODE_ENV === "production") {
  console.error("Refusing to run the flow harness with NODE_ENV=production.");
  process.exit(1);
}

const BASE = "http://localhost:3000";
const TEACHER = { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" };

const errors = [];
const net = [];

function wire(page) {
  page.on("console", (m) => {
    if (m.type() === "error") errors.push("console: " + m.text().slice(0, 250));
  });
  page.on("pageerror", (e) => errors.push("pageerror: " + String(e).slice(0, 300)));
  page.on("response", (r) => {
    if (r.status() >= 400)
      net.push(`${r.status()} ${r.request().method()} ${r.url().replace(BASE, "")}`);
  });
}

function report(label) {
  if (errors.length || net.length) {
    console.log(`\n!! [${label}]`);
    for (const e of [...new Set(errors)]) console.log("   " + e);
    for (const n of [...new Set(net)]) console.log("   " + n);
    errors.length = 0;
    net.length = 0;
    return true;
  }
  return false;
}

async function describe(page) {
  return page.evaluate(() => {
    const stepper = document.querySelector('nav[aria-label="Course setup stages"]');
    return {
      url: location.pathname + location.search,
      h1: document.querySelector("h1")?.textContent?.trim() ?? null,
      stepper: stepper
        ? [...stepper.querySelectorAll("button")].map((b) => ({
            t: (b.textContent || "").replace(/\s+/g, " ").trim(),
            disabled: b.hasAttribute("disabled"),
            current: b.getAttribute("aria-current") === "step",
          }))
        : null,
      // Anything that looks like a form the stage expects the user to fill.
      inputs: [...document.querySelectorAll("main input, main select, main textarea")]
        .slice(0, 12)
        .map((el) => ({
          tag: el.tagName.toLowerCase(),
          name: el.getAttribute("name"),
          label: el.getAttribute("aria-label") || el.getAttribute("placeholder"),
        })),
      buttons: [...document.querySelectorAll("main button")]
        .slice(0, 14)
        .map((b) => ({
          t: (b.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40),
          disabled: b.hasAttribute("disabled"),
        })),
      body: (document.body.innerText || "").replace(/\s+/g, " ").slice(0, 300),
    };
  });
}

async function run() {
  const outDir = process.argv[2] || "newcourse-out";
  await mkdir(outDir, { recursive: true });

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  wire(page);

  await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', TEACHER.email);
  await page.fill('input[name="password"]', TEACHER.password);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/teacher/, { timeout: 25000 }).catch(() => {});
  await page.waitForTimeout(1800);
  report("sign-in");

  // ---- open the roster and press Create course ---------------------------
  await page.goto(`${BASE}/teacher/courses`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${outDir}/01-roster.png`, fullPage: true });

  const createBtn = page.getByRole("button", { name: /create course/i }).first();
  const hasCreate = await createBtn.count();
  console.log("Create course button present:", hasCreate > 0);
  if (!hasCreate) {
    console.log("NO CREATE BUTTON, stopping.");
    await browser.close();
    return;
  }

  await createBtn.click();
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${outDir}/02-create-dialog.png`, fullPage: true });
  report("open create dialog");

  const dialog = await page.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return null;
    return {
      heading: d.querySelector("h2,h3")?.textContent?.trim() ?? null,
      inputs: [...d.querySelectorAll("input, select, textarea")].map((el) => ({
        tag: el.tagName.toLowerCase(),
        name: el.getAttribute("name"),
        label: el.getAttribute("aria-label") || el.getAttribute("placeholder"),
        required: el.hasAttribute("required"),
      })),
      buttons: [...d.querySelectorAll("button")].map((b) =>
        (b.textContent || "").replace(/\s+/g, " ").trim()
      ),
    };
  });
  console.log("\n[create dialog]", JSON.stringify(dialog, null, 2));

  if (!dialog) {
    console.log("DIALOG DID NOT OPEN, stopping.");
    await browser.close();
    return;
  }

  // ---- fill and submit ---------------------------------------------------
  // The dialog's inputs are associated by `id`/<label>, not `name`, so fill
  // them the way a user does: by their visible label.
  const stamp = Date.now().toString().slice(-6);
  await page.fill("#course-name", `QA Flow Course ${stamp}`);
  await page.fill("#course-code", `QA${stamp}`);
  await page.fill("#course-semester", "2026 Spring");
  await page.fill("#course-description", "Created by the setup-flow harness.");

  // Language is a Base UI Select, not a native <select>.
  await page.getByRole("combobox").first().click().catch(async () => {
    await page.locator('button:has-text("Select language")').click();
  });
  await page.waitForTimeout(500);
  await page
    .getByRole("option", { name: "Chinese" })
    .first()
    .click()
    .catch(async () => {
      await page.locator('[role="option"]', { hasText: "Chinese" }).first().click();
    });
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${outDir}/03-filled.png`, fullPage: true });

  await page
    .locator('[role="dialog"] button[type="submit"]')
    .first()
    .click()
    .catch((e) => console.log("submit click failed:", e.message));

  // The create mutation should route into setup.
  await page.waitForURL(/\/setup/, { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outDir}/04-after-create.png`, fullPage: true });
  const brokeCreate = report("after create");

  const after = await describe(page);
  console.log("\n[after create]", JSON.stringify(after, null, 2).slice(0, 2200));

  if (!/\/setup/.test(after.url)) {
    console.log("\n>>> DID NOT LAND IN SETUP. url =", after.url);
  }

  // ---- walk the stages on the NEW course ---------------------------------
  const base = after.url.split("?")[0];
  for (const stage of ["basics", "sources", "schedule", "review", "publish"]) {
    await page.goto(`${BASE}${base}?stage=${stage}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${outDir}/05-${stage}.png`, fullPage: true });
    const snap = await describe(page);
    console.log(`\n[new course · ${stage}] h1=${snap.h1}`);
    console.log(
      "  stepper: " +
        (snap.stepper
          ? snap.stepper
              .map((s) => `${s.t.replace(/\s+/g, "")}${s.current ? "*" : ""}${s.disabled ? "(locked)" : ""}`)
              .join(" | ")
          : "MISSING")
    );
    console.log("  buttons: " + JSON.stringify(snap.buttons));
    console.log("  body: " + snap.body.slice(0, 220));
    report(`new course ${stage}`);
  }

  await browser.close();
  if (brokeCreate) process.exitCode = 1;
}

run().catch((e) => {
  console.error("HARNESS ERROR:", e);
  process.exit(1);
});
