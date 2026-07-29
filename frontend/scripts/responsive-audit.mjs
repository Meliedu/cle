// Release-acceptance audit, measured in a real browser.
//
// The handoff's release criteria cannot be checked from source alone:
//
//   Targets      High-frequency controls and touch actions meet 44x44 CSS px
//                implementation targets; adjacent targets retain separation.
//                Verification: browser-computed hitbox audit at desktop and
//                mobile viewports.
//   Responsive   No clipped rows, off-centre controls, floating text, or
//                horizontal page scroll at 1440x900, 1280x800, 1024x768, and
//                390x844.
//   Focus        Visible focus is not clipped, obscured, or color-only.
//
// jsdom has no layout, so the unit guards can only assert that the right
// classes are present. This script measures the rendered result.
//
// Usage: node scripts/responsive-audit.mjs [outDir]
import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";

if (process.env.NODE_ENV === "production") {
  console.error("Refusing to run the audit harness with NODE_ENV=production.");
  process.exit(1);
}

const BASE = "http://localhost:3000";
const CREDS = {
  teacher: { email: "meli.teacher@ust.hk", password: "MeliDemo2026!" },
  student: { email: "meli.student@connect.ust.hk", password: "MeliDemo2026!" },
};

/** The four viewports the release contract names. */
const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900, touch: false },
  { name: "1280x800", width: 1280, height: 800, touch: false },
  { name: "1024x768", width: 1024, height: 768, touch: false },
  // 390x844 is a phone, so it must be emulated as one. Without `hasTouch` the
  // browser reports `pointer: fine` and every `pointer-coarse` touch-target
  // floor is inert, so the mobile pass would silently measure desktop sizing.
  { name: "390x844", width: 390, height: 844, touch: true },
];

const ROUTES = {
  teacher: [
    ["home", "/teacher/dashboard"],
    ["courses", "/teacher/courses"],
    ["calendar", "/teacher/calendar"],
    ["course-overview", null], // resolved from the roster
    ["sessions", null],
    ["students", null],
  ],
  student: [
    ["home", "/student/dashboard"],
    ["courses", "/student/courses"],
    ["calendar", "/student/calendar"],
  ],
};

/**
 * Measured in-page. Returns every violation of the rendered criteria.
 *
 * `44` is the CSS-px floor from the contract. A control smaller than that in
 * EITHER dimension is reported, with the exception of inline text links inside
 * a paragraph, which are not touch targets and whose hitbox is the line box.
 */
const AUDIT = `(() => {
  const MIN = 44;
  const problems = [];

  // 1. Horizontal page scroll.
  const de = document.documentElement;
  if (de.scrollWidth > de.clientWidth + 1) {
    problems.push({
      kind: "horizontal-scroll",
      detail: \`scrollWidth \${de.scrollWidth} > clientWidth \${de.clientWidth}\`,
    });
  }

  // 2. Any element overflowing the viewport on the x axis.
  const vw = de.clientWidth;
  for (const el of document.querySelectorAll("body *")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = getComputedStyle(el);
    if (cs.position === "fixed") continue;
    if (r.right > vw + 1) {
      // Content inside a scrollable ancestor is INTENDED to exceed the
      // viewport: a wide table in an overflow-x:auto container is the
      // correct responsive pattern, not a clipped row. Only unscrollable
      // overflow is a defect.
      let scrollable = false;
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        const acs = getComputedStyle(a);
        if (acs.overflowX === "auto" || acs.overflowX === "scroll") {
          scrollable = true;
          break;
        }
      }
      if (scrollable) continue;

      // Only report the outermost offender to avoid a cascade of children.
      const parent = el.parentElement;
      const pr = parent ? parent.getBoundingClientRect() : null;
      if (pr && pr.right > vw + 1) continue;
      problems.push({
        kind: "overflow-x",
        detail: \`<\${el.tagName.toLowerCase()}> right \${Math.round(r.right)} > viewport \${vw}\`,
        text: (el.textContent || "").trim().slice(0, 60),
      });
    }
  }

  // 3. Touch-target size for real controls.
  const controls = document.querySelectorAll(
    'button, a[href], select, input:not([type=hidden]), [role="tab"], [role="button"]'
  );
  for (const el of controls) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue; // not rendered
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") continue;
    if (el.hasAttribute("disabled")) continue;

    // Inline links inside running text are not touch targets.
    const inline = cs.display === "inline" && el.closest("p, li, dd, dt, span");
    if (inline) continue;

    if (r.height < MIN - 0.5 || r.width < MIN - 0.5) {
      problems.push({
        kind: "small-target",
        detail: \`\${Math.round(r.width)}x\${Math.round(r.height)}\`,
        text:
          (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 50) ||
          el.tagName.toLowerCase(),
      });
    }
  }

  // 4. Focus suppressed with no visible replacement.
  //
  // Only an element that BOTH removes its outline via the outline-none
  // utility AND declares no focus-visible replacement is a defect. A resting
  // computed outline of "none" is the browser default for most elements and
  // says nothing about focus, so it cannot be the signal on its own.
  for (const el of controls) {
    const cls =
      el.className && el.className.baseVal !== undefined
        ? el.className.baseVal
        : String(el.className || "");
    const suppresses = /(^|\s)outline-none(\s|$)/.test(cls);
    const replaces = /focus-visible:/.test(cls);
    if (suppresses && !replaces) {
      problems.push({
        kind: "focus-suppressed",
        detail: "outline-none with no focus-visible replacement",
        text: (el.textContent || "").trim().slice(0, 50) || el.tagName.toLowerCase(),
      });
    }
  }

  return problems;
})()`;

async function login(context, role) {
  const page = await context.newPage();
  await page.goto(`${BASE}/sign-in`, { waitUntil: "networkidle" });
  await page.fill('input[name="email"]', CREDS[role].email);
  await page.fill('input[name="password"]', CREDS[role].password);
  await page.click('button[type="submit"]');
  // Do NOT swallow this. A silent login failure sends every later goto to
  // /sign-in, which yields few violations and prints "PASS: no rendered
  // violations" having audited nothing but the login page.
  try {
    await page.waitForURL(/\/(teacher|student|dashboard)/, { timeout: 25000 });
  } catch {
    const at = page.url();
    await page.close();
    throw new Error(
      `login failed for ${role} (${CREDS[role].email}); still at ${at}. ` +
        `Check the demo seed and that this host allows email/password sign-in.`
    );
  }
  await page.waitForTimeout(2000);
  await page.close();
}

/** Follow the roster into a real course so course-scoped routes are covered. */
async function resolveCourseRoutes(page) {
  await page.goto(`${BASE}/teacher/courses`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  const href = await page.evaluate(() => {
    const link = document.querySelector('a[href^="/teacher/courses/"]');
    return link ? link.getAttribute("href") : null;
  });
  if (!href) return null;
  const base = href.split("?")[0].replace(/\/setup$/, "");
  return base;
}

let audited = 0;

async function run() {
  const outDir = process.argv[2] || "audit-out";
  await mkdir(outDir, { recursive: true });

  const browser = await chromium.launch();
  const findings = [];

  for (const role of ["teacher", "student"]) {
    let context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
    });
    await login(context, role);

    let page = await context.newPage();
    let routes = ROUTES[role].filter(([, url]) => url !== null);

    if (role === "teacher") {
      const courseBase = await resolveCourseRoutes(page);
      if (courseBase) {
        routes = routes.concat([
          ["course-overview", courseBase],
          ["sessions", `${courseBase}/sessions`],
          ["students", `${courseBase}/students`],
          ["materials", `${courseBase}/materials`],
        ]);
      }
    }

    for (const viewport of VIEWPORTS) {
      // A touch pass needs its own context: `hasTouch` is a context option,
      // not something `setViewportSize` can change.
      if (viewport.touch) {
        await page.close();
        await context.close();
        context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          hasTouch: true,
          isMobile: true,
        });
        await login(context, role);
        page = await context.newPage();
      } else {
        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });
      }
      for (const [label, url] of routes) {
        try {
          await page.goto(`${BASE}${url}`, {
            waitUntil: "networkidle",
            timeout: 30000,
          });
          await page.waitForTimeout(900);
          // A silent redirect to /sign-in means this route was never audited.
          // Counting it as "no violations" is how an audit reports success
          // having measured nothing.
          const landedAt = new URL(page.url()).pathname;
          if (/\/sign-in|\/sign-up/.test(landedAt) && !/sign-in|sign-up/.test(url)) {
            findings.push({
              role,
              viewport: viewport.name,
              label,
              url,
              problems: [
                { kind: "not-audited", detail: `redirected to ${landedAt}; session lost` },
              ],
            });
            continue;
          }
          audited += 1;
          const problems = await page.evaluate(AUDIT);
          if (problems.length) {
            findings.push({ role, viewport: viewport.name, label, url, problems });
          }
          await page.screenshot({
            path: `${outDir}/${role}-${label}-${viewport.name}.png`,
            fullPage: false,
          });
        } catch (e) {
          findings.push({
            role,
            viewport: viewport.name,
            label,
            url,
            problems: [{ kind: "load-error", detail: e.message.slice(0, 160) }],
          });
        }
      }
    }
    await page.close();
    await context.close();
  }

  await browser.close();

  await writeFile(
    `${outDir}/findings.json`,
    JSON.stringify(findings, null, 2),
    "utf8"
  );

  // Summarise by kind so the report is readable.
  const byKind = {};
  for (const f of findings) {
    for (const p of f.problems) {
      const key = `${p.kind}`;
      byKind[key] = byKind[key] || [];
      byKind[key].push(
        `${f.role}/${f.label} @${f.viewport}: ${p.detail}${p.text ? `: "${p.text}"` : ""}`
      );
    }
  }

  if (!Object.keys(byKind).length) {
    console.log(`PASS: no rendered violations across ${audited} audited page loads.`);
    return;
  }
  // Findings must gate. Previously this only printed, so the audit could never
  // fail a caller even when it found real violations.
  process.exitCode = 1;
  for (const [kind, items] of Object.entries(byKind)) {
    console.log(`\n### ${kind} (${items.length})`);
    // Collapse duplicates across viewports.
    const seen = new Set();
    for (const item of items) {
      if (seen.has(item)) continue;
      seen.add(item);
      console.log(`  ${item}`);
    }
  }
}

run().catch((e) => {
  console.error(e);
  process.exit(1);
});
