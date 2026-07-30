/**
 * Full placement end-to-end harness: journey, UI/UX, accessibility, layout.
 *
 * The unit and API suites check rules. The browser checks whether a person can
 * actually get through, and whether the page tells them the truth while they do.
 * Everything here is a check that has already caught a real defect at least once,
 * or that guards one that was caught.
 *
 * Screenshots are written to a durable directory (default
 * ../docs/placement-flow-screenshots) so the whole flow can be reviewed later.
 *
 *   node scripts/placement-e2e.mjs [outDir]
 *
 * Requires a published version: backend/scripts/seed_placement_dev.py
 */

import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const OUT = resolve(process.argv[2] ?? "../docs/placement-flow-screenshots");
const CREDS = {
  teacher: { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" },
  student: { email: "meli.student@connect.ust.hk", password: "MeliDemo2026!" },
};

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 812, hasTouch: true },
  { name: "tablet", width: 768, height: 1024, hasTouch: true },
  { name: "desktop", width: 1440, height: 900, hasTouch: false },
];

const findings = [];
const notes = [];
let shotIndex = 0;

const note = (m) => { notes.push(m); console.log(`  ${m}`); };
const fail = (m) => { findings.push(m); console.log(`  ! ${m}`); };

/** Every --color-* token the design system actually defines. */
const DEFINED_TOKENS = (() => {
  const css = readFileSync(resolve("src/styles/tokens.css"), "utf8");
  return new Set([...css.matchAll(/^\s*(--color-[a-z0-9-]+)\s*:/gm)].map((m) => m[1]));
})();

async function shot(page, name) {
  shotIndex += 1;
  const file = `${String(shotIndex).padStart(2, "0")}-${name}.png`;
  await page.screenshot({ path: `${OUT}/${file}`, fullPage: true });
  return file;
}

// ---------------------------------------------------------------------------
// Page-level audits
// ---------------------------------------------------------------------------

/**
 * An undefined `var(--x)` with no fallback is invalid at computed-value time,
 * so the property silently falls back to inherited/initial. Colour-only meaning
 * then disappears with no error anywhere. This is how `--color-danger` (never
 * defined; the token is `--color-error`) shipped unnoticed.
 */
async function auditTokens(page, label) {
  const used = await page.evaluate(() => {
    const out = new Set();
    for (const el of document.querySelectorAll("*")) {
      for (const cls of el.classList) {
        // `var(--a,var(--b))` is legal: only the FIRST name must exist for the
        // declaration to be safe, so a fallback chain is not a finding.
        for (const m of cls.matchAll(/var\((--color-[a-z0-9-]+)\s*(,)?/g)) {
          if (!m[2]) out.add(m[1]);
        }
      }
    }
    return [...out];
  });
  const undefinedTokens = used.filter((t) => !DEFINED_TOKENS.has(t));
  if (undefinedTokens.length) {
    fail(
      `${label}: undefined CSS token(s) with no fallback: ${undefinedTokens.join(", ")}` +
        " — the property silently falls back to inherited/initial"
    );
  }
}

/**
 * Text contrast, measured from what the browser actually computed rather than
 * from the token table, so an opacity modifier or an unexpected inherit is
 * caught too. WCAG 2.2 AA: 4.5:1 for body text, 3:1 for large text.
 */
async function auditContrast(page, label) {
  const bad = await page.evaluate(() => {
    const lin = (u) => (u <= 0.04045 ? u / 12.92 : ((u + 0.055) / 1.055) ** 2.4);
    const lum = ([r, g, b]) =>
      0.2126 * lin(r / 255) + 0.7152 * lin(g / 255) + 0.0722 * lin(b / 255);

    // This project authors colour in oklch, and getComputedStyle hands back
    // `oklch(...)` verbatim. Parsing that string as RGB reads L, C, H as red,
    // green, blue and reports near-black for everything, which made a dark
    // heading on a light page look like 1.5:1. Let the browser do the
    // conversion: paint onto a canvas and read the pixel back.
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });

    const cache = new Map();
    function toRgba(colour) {
      if (cache.has(colour)) return cache.get(colour);
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = "#000";
      ctx.fillStyle = colour;
      // An unparseable value leaves fillStyle at the previous colour; treat
      // that as unknown rather than silently reporting black.
      ctx.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data;
      const out = { rgb: [r, g, b], alpha: a / 255 };
      cache.set(colour, out);
      return out;
    }

    /** Composite a possibly-translucent colour over what is behind it. */
    function over(fg, bg) {
      return fg.rgb.map((c, i) => c * fg.alpha + bg[i] * (1 - fg.alpha));
    }

    function backdrop(el) {
      const stack = [];
      for (let n = el; n; n = n.parentElement) {
        const c = toRgba(getComputedStyle(n).backgroundColor);
        if (c.alpha > 0.999) {
          let base = c.rgb;
          for (let i = stack.length - 1; i >= 0; i -= 1) base = over(stack[i], base);
          return base;
        }
        if (c.alpha > 0) stack.push(c);
      }
      let base = [255, 255, 255];
      for (let i = stack.length - 1; i >= 0; i -= 1) base = over(stack[i], base);
      return base;
    }

    const out = [];
    const seen = new Set();
    for (const el of document.querySelectorAll("main *")) {
      const text = [...el.childNodes]
        .filter((n) => n.nodeType === 3)
        .map((n) => n.textContent.trim())
        .join(" ")
        .trim();
      if (!text) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") continue;
      // WCAG 1.4.3 exempts inactive controls, and the shared Button dims itself
      // with disabled:opacity-50 — auditing that reports a failure for a state
      // the standard does not cover.
      if (el.closest("[disabled], [aria-disabled='true']")) continue;
      const size = parseFloat(cs.fontSize);
      const weight = Number(cs.fontWeight) || 400;
      const large = size >= 24 || (size >= 18.66 && weight >= 700);
      const need = large ? 3 : 4.5;

      const bg = backdrop(el);
      const fgRaw = toRgba(cs.color);
      if (fgRaw.alpha === 0) continue;
      const fg = over(fgRaw, bg);
      const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
      const ratio = (hi + 0.05) / (lo + 0.05);
      if (ratio < need) {
        const key = `${cs.color}|${Math.round(size)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({ text: text.slice(0, 44), ratio: ratio.toFixed(2), need, size: Math.round(size) });
      }
    }
    return out.slice(0, 4);
  });
  for (const b of bad) {
    fail(`${label}: contrast ${b.ratio}:1 (needs ${b.need}) at ${b.size}px — "${b.text}"`);
  }
}

/** The page body must never scroll sideways; wide content scrolls inside itself. */
async function auditOverflow(page, label, width) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    const scroller = document.querySelector("main") ?? doc;
    return {
      docOver: doc.scrollWidth - doc.clientWidth,
      mainOver: scroller.scrollWidth - scroller.clientWidth,
      widest: (() => {
        let worst = null;
        for (const el of document.querySelectorAll("main *")) {
          const r = el.getBoundingClientRect();
          if (r.right > window.innerWidth + 1) {
            const over = Math.round(r.right - window.innerWidth);
            if (!worst || over > worst.over) {
              worst = { over, tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 70) };
            }
          }
        }
        return worst;
      })(),
    };
  });
  if (overflow.docOver > 1 || overflow.mainOver > 1) {
    const w = overflow.widest;
    fail(
      `${label} @${width}px: horizontal overflow (doc +${overflow.docOver}, main +${overflow.mainOver})` +
        (w ? ` — widest: <${w.tag}> "${w.cls}" +${w.over}px` : "")
    );
  }
}

/** Untranslated key paths and leaked exception text. */
async function auditText(page, label) {
  const problems = await page.evaluate(() => {
    const main = document.querySelector("main") ?? document.body;
    const text = (main.innerText || "").trim();
    const out = [];
    if (text.length < 20) out.push(`effectively blank (${text.length} chars)`);
    const keys = (text.match(/\b[a-z][a-zA-Z0-9]*(?:\.[a-z][a-zA-Z0-9_]*){2,}\b/g) || [])
      .filter((k) => !/\.(com|org|net|hk|edu|io|js|ts|png|jpg|pdf)$/i.test(k));
    if (keys.length) out.push(`raw i18n key: ${keys.slice(0, 3).join(", ")}`);
    const leak = text.match(/\b\w*(?:Error|Exception)\b\s*:|Traceback|psycopg|sqlalchemy|asyncpg|\bNoneType\b/i);
    if (leak) out.push(`leaked internals: ${leak[0].slice(0, 60)}`);
    if (!document.querySelector("h1, h2")) out.push("no h1/h2 heading");
    return out;
  });
  for (const p of problems) fail(`${label}: ${p}`);
}

/** Touch targets must clear 44px on coarse pointers. */
async function auditTouchTargets(page, label) {
  const small = await page.evaluate(() => {
    const out = [];
    const sel = 'main button, main a[href], main select, main input[type="checkbox"], main input[type="radio"]';
    for (const el of document.querySelectorAll(sel)) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) continue;
      // A control inside a label big enough to hit is fine.
      const label = el.closest("label");
      const box = label ? label.getBoundingClientRect() : r;
      if (box.height < 44 - 0.5) {
        out.push(`${el.tagName.toLowerCase()}"${(el.textContent || "").trim().slice(0, 24)}" ${Math.round(box.height)}px`);
      }
    }
    return out.slice(0, 5);
  });
  if (small.length) fail(`${label}: touch target(s) under 44px: ${small.join("; ")}`);
}

async function auditAll(page, label, width, { touch = false } = {}) {
  await auditTokens(page, label);
  await auditContrast(page, label);
  await auditOverflow(page, label, width);
  await auditText(page, label);
  if (touch) await auditTouchTargets(page, label);
}

// ---------------------------------------------------------------------------
// Journey
// ---------------------------------------------------------------------------

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

async function studentJourney(context, viewport) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

  await page.goto(`${BASE}/student/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await shot(page, `student-intro-${viewport.name}`);
  await auditAll(page, "intro", viewport.width, { touch: viewport.hasTouch });

  const intro = await page.locator("main").innerText();
  if (!/not an official HSK|並非官方/i.test(intro)) fail("intro omits the claim boundary");
  if (!/30 questions|30 題/i.test(intro)) fail("intro omits the item count");
  if (!/not statistically equated|未經統計等化/i.test(intro)) {
    fail("intro omits the form-comparability caveat");
  }
  note("intro states purpose, structure and claim boundary");

  await page.getByRole("button", { name: /start the screener/i }).click();
  await page.waitForTimeout(1500);
  await shot(page, `student-eligibility-${viewport.name}`);
  await auditAll(page, "eligibility", viewport.width, { touch: viewport.hasTouch });

  const form = (await page.locator("main").innerText()).match(/Form ([A-E])/);
  note(`form allocated: ${form ? form[1] : "unknown"}`);

  for (let i = 0; i < 2; i += 1) {
    const btn = page.getByRole("button", { name: /i understand, continue/i });
    if ((await btn.count()) === 0) break;
    await btn.click();
    await page.waitForTimeout(1000);
  }
  await shot(page, `student-instructions-${viewport.name}`);
  await auditAll(page, "instructions", viewport.width, { touch: viewport.hasTouch });

  const begin = page.getByRole("button", { name: /start the timer and begin/i });
  if ((await begin.count()) === 0) { fail("never reached the instructions screen"); await page.close(); return; }
  if (await begin.isEnabled()) fail("the timer can start before the audio check is confirmed");
  await page.getByRole("checkbox").first().check();
  if (!(await begin.isEnabled())) fail("confirming audio did not enable the start button");

  // The paper must not be reachable before the clock starts.
  const preItems = await page.locator('main input[type="radio"]').count();
  if (preItems > 0) fail("questions are visible before the timer starts");
  note("paper withheld until the timer starts");

  await begin.click();
  await page.waitForTimeout(2000);
  await shot(page, `student-sitting-q1-${viewport.name}`);
  await auditAll(page, "sitting", viewport.width, { touch: viewport.hasTouch });

  // Tab order: the pager must be reachable without traversing 30 map buttons.
  const tabsToNext = await page.evaluate(() => {
    const focusable = [...document.querySelectorAll(
      'main button, main a[href], main select, main input, main [tabindex]:not([tabindex="-1"])'
    )].filter((el) => !el.disabled && el.offsetParent !== null);
    const nextIndex = focusable.findIndex((el) => /next|submit/i.test(el.textContent || ""));
    return { nextIndex, total: focusable.length };
  });
  if (tabsToNext.nextIndex > 12) {
    fail(`pager is ${tabsToNext.nextIndex} tab stops away; a keyboard user traverses the map first`);
  } else {
    note(`pager reachable in ${tabsToNext.nextIndex} tab stops`);
  }

  const map = page.locator("nav ul li button");
  const total = await map.count();
  if (total !== 30) fail(`question map shows ${total}, expected 30`);

  let sequenceSeen = false;
  for (let i = 0; i < total; i += 1) {
    await map.nth(i).click();
    await page.waitForTimeout(90);
    const selects = page.locator("main select");
    const radios = page.locator('main input[type="radio"]');
    if ((await selects.count()) >= 3) {
      sequenceSeen = true;
      // Half-fill first: the map must NOT then call it answered.
      await selects.nth(0).selectOption("C");
      await page.waitForTimeout(120);
      const halfLabel = await map.nth(i).getAttribute("aria-label");
      if (/, answered/i.test(halfLabel ?? "")) {
        fail("a half-filled ordering item is marked answered in the question map");
      } else {
        note("half-filled ordering item is not marked answered");
      }
      await selects.nth(1).selectOption("A");
      await selects.nth(2).selectOption("B");
      await page.waitForTimeout(120);
    } else if ((await radios.count()) > 0) {
      await radios.first().check();
    } else {
      fail(`question ${i + 1} offered no answer control`);
    }
  }
  if (!sequenceSeen) fail("never encountered the ordering item");

  await page.waitForTimeout(1200);
  const progress = await page.locator('[role="progressbar"]').first().getAttribute("aria-valuenow");
  if (progress !== "30") fail(`progress reports ${progress}, expected 30`);
  await shot(page, `student-sitting-complete-${viewport.name}`);

  await page.getByRole("button", { name: /review and submit/i }).click();
  await page.waitForTimeout(600);
  await shot(page, `student-confirm-${viewport.name}`);
  const confirm = await page.locator("main").innerText();
  if (!/cannot change your answers/i.test(confirm)) {
    fail("submit confirmation does not warn that answers are final");
  }

  await page.getByRole("button", { name: /^submit$/i }).click();
  await page.waitForTimeout(3500);
  await shot(page, `student-pending-${viewport.name}`);
  await auditAll(page, "pending", viewport.width, { touch: viewport.hasTouch });

  const pending = await page.locator("main").innerText();
  if (!/with CLE|CLE review/i.test(pending)) fail("no pending-review state after submit");
  for (const leak of ["LANG151", "/30", "Band "]) {
    if (pending.includes(leak)) fail(`pending screen leaks result detail: ${leak}`);
  }
  note("pending review shown; no score, band or course leaked");

  if (consoleErrors.length) fail(`console errors: ${consoleErrors.slice(0, 2).join(" | ")}`);
  await page.close();
}

async function teacherJourney(context, viewport) {
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(`pageerror: ${e.message}`));

  await page.goto(`${BASE}/teacher/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await shot(page, `teacher-queue-${viewport.name}`);
  await auditAll(page, "review queue", viewport.width, { touch: viewport.hasTouch });

  const open = page.getByRole("link", { name: /^open$/i }).first();
  if ((await open.count()) === 0) { fail("submitted attempt not in the review queue"); await page.close(); return; }
  await open.click();
  try {
    await page.getByRole("heading", { name: /placement attempt/i }).waitFor({ timeout: 30000 });
  } catch { fail("evidence page never left its loading state"); }
  await page.waitForTimeout(800);
  await shot(page, `teacher-evidence-${viewport.name}`);
  await auditAll(page, "evidence", viewport.width, { touch: viewport.hasTouch });

  const evidence = await page.locator("main").innerText();
  for (const [needle, what] of [
    [/Answer sheet/i, "answer sheet"],
    [/Reference band profile/i, "band profile"],
    [/Skill evidence/i, "skill evidence"],
  ]) {
    if (!needle.test(evidence)) fail(`evidence bundle missing the ${what}`);
  }
  // Skill evidence must read in the order the learner sat the sections.
  const order = ["Listening", "Language use", "Reading"].map((s) => evidence.indexOf(s));
  if (!(order[0] < order[1] && order[1] < order[2])) {
    fail(`skill evidence out of blueprint order (indices ${order.join(",")})`);
  } else {
    note("skill evidence in blueprint order");
  }

  // The wide answer sheet must scroll inside its own container.
  const tableScrolls = await page.evaluate(() => {
    const t = document.querySelector("main table");
    if (!t) return null;
    const box = t.closest("[class*='overflow-x']");
    return Boolean(box);
  });
  if (tableScrolls === false) fail("the answer-sheet table is not in a scroll container");

  await page.getByRole("radio", { name: /approve/i }).first().check();
  await page.getByRole("button", { name: /record decision/i }).click();
  await page.waitForTimeout(2500);
  await shot(page, `teacher-approved-${viewport.name}`);

  await page.getByRole("radio", { name: /release to the student/i }).first().check();
  await page.getByRole("button", { name: /record decision/i }).click();
  await page.waitForTimeout(2500);
  await shot(page, `teacher-released-${viewport.name}`);

  if (!/released/i.test(await page.locator("main").innerText())) {
    fail("attempt does not show as released after release");
  }
  note("approved and released");
  if (consoleErrors.length) fail(`teacher console errors: ${consoleErrors.slice(0, 2).join(" | ")}`);
  await page.close();
}

async function studentResult(context, viewport) {
  const page = await context.newPage();
  await page.goto(`${BASE}/student/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);
  await shot(page, `student-result-${viewport.name}`);
  await auditAll(page, "result", viewport.width, { touch: viewport.hasTouch });

  const text = await page.locator("main").innerText();
  if (!/LANG15\d\d/.test(text)) fail("released recommendation not shown to the student");
  if (!/not an official HSK|並非官方/i.test(text)) fail("released result drops the claim boundary");
  note("student sees the released recommendation with its claim boundary");
  await page.close();
}

/** The zh-Hant surface must be fully translated, especially the claim boundary. */
async function chineseCheck(context) {
  const page = await context.newPage();
  await page.goto(`${BASE}/student/placement`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const toggle = page.getByRole("button", { name: /繁體中文|English/ }).first();
  if ((await toggle.count()) === 0) {
    note("no language toggle on this page; skipped the zh check");
    await page.close();
    return;
  }
  await toggle.click();
  await page.waitForTimeout(2000);
  await shot(page, "student-result-zh");

  const text = await page.locator("main").innerText();
  // The claim boundary was the one English hole on an otherwise zh page.
  const englishSentences = text.match(/[A-Za-z][A-Za-z ,'()-]{40,}/g) || [];
  if (englishSentences.length) {
    fail(`zh page still shows English prose: "${englishSentences[0].slice(0, 70)}"`);
  } else {
    note("zh-Hant page carries no untranslated English prose");
  }
  await page.close();
}

// ---------------------------------------------------------------------------

async function run() {
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();

  // The journey runs once end-to-end (it consumes an attempt), on desktop.
  // The other viewports re-audit the static screens for layout only.
  const desktop = VIEWPORTS[2];
  console.log(`student journey @${desktop.width}px:`);
  const studentCtx = await browser.newContext({ viewport: { width: desktop.width, height: desktop.height } });
  await login(studentCtx, "student");
  await studentJourney(studentCtx, desktop);

  console.log("teacher review:");
  const teacherCtx = await browser.newContext({ viewport: { width: desktop.width, height: desktop.height } });
  await login(teacherCtx, "teacher");
  await teacherJourney(teacherCtx, desktop);

  console.log("student result:");
  await studentResult(studentCtx, desktop);
  await chineseCheck(studentCtx);

  // Layout sweep of the reachable screens at the narrow breakpoints.
  for (const vp of VIEWPORTS.slice(0, 2)) {
    console.log(`layout sweep @${vp.width}px:`);
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      hasTouch: vp.hasTouch,
    });
    await login(ctx, "student");
    const p = await ctx.newPage();
    await p.goto(`${BASE}/student/placement`, { waitUntil: "networkidle" });
    await p.waitForTimeout(2000);
    await shot(p, `student-result-${vp.name}`);
    await auditAll(p, `student result @${vp.width}`, vp.width, { touch: vp.hasTouch });
    await p.close();
    await ctx.close();

    const tctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      hasTouch: vp.hasTouch,
    });
    await login(tctx, "teacher");
    const tp = await tctx.newPage();
    await tp.goto(`${BASE}/teacher/placement`, { waitUntil: "networkidle" });
    await tp.waitForTimeout(2000);
    await shot(tp, `teacher-queue-${vp.name}`);
    await auditAll(tp, `review queue @${vp.width}`, vp.width, { touch: vp.hasTouch });
    await tp.close();
    await tctx.close();
  }

  await studentCtx.close();
  await teacherCtx.close();
  await browser.close();

  writeFileSync(
    `${OUT}/report.json`,
    JSON.stringify({ findings, notes, screenshots: shotIndex }, null, 2)
  );
  console.log(`\n${shotIndex} screenshots in ${OUT}`);
  if (findings.length) {
    console.log(`\n${findings.length} FINDING(S):`);
    for (const f of findings) console.log(`  - ${f}`);
    process.exitCode = 1;
  } else {
    console.log("\nPASS: no findings across journey, layout, a11y and copy checks.");
  }
}

run().catch((e) => { console.error(e); process.exit(1); });
