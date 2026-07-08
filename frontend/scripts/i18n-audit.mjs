// i18n key audit for the P4–P7 UI (reports, memory, insights, activities,
// practice, calendar, course workspace, materials, setup + the teacher/student
// route trees).
//
// Two checks:
//   1. MISSING KEYS (hard signal): every next-intl key REFERENCED via the real
//      idiom — `const t = useTranslations("ns")` / `await getTranslations("ns")`
//      then `t("sub.key")` — must resolve to a real leaf/node in
//      messages/en.json. A referenced key that is absent is a violation.
//   2. HARDCODED STRINGS (soft signal): likely user-facing literals in JSX text
//      or text-bearing attributes that should be i18n keys. Reported as
//      warnings only (heuristic — tuned for low false positives), NEVER a hard
//      fail, so the guard test stays stable.
//
// Usage (from frontend/):  node scripts/i18n-audit.mjs
// Exit code: 1 if any referenced key is missing, else 0. Importable via
// `runAudit()` for the vitest guard.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = resolve(__dirname, "..");
const MESSAGES_PATH = join(FRONTEND_ROOT, "messages", "en.json");

// P4–P7 component dirs + the teacher/student route trees. Only dirs that
// actually exist are scanned (the plan's list is a superset).
const COMPONENT_DIRS = [
  "reports",
  "memory",
  "student-reports",
  "teacher-insights",
  "student-insights",
  "activities",
  "student-activities",
  "practice",
  "calendar",
  "course",
  "student-workspace",
  "materials",
  "setup",
];
const ROUTE_DIRS = [
  join("app", "(app)", "teacher"),
  join("app", "(app)", "student"),
];

/** Recursively collect .ts/.tsx source files, excluding tests/stories. */
function collectSourceFiles(dir) {
  let out = [];
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return out; // dir absent — the plan list is a superset
  }
  for (const entry of entries) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      out = out.concat(collectSourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry)) continue;
    if (/\.(test|spec|stories)\.tsx?$/.test(entry)) continue;
    out.push(full);
  }
  return out;
}

function scanRoots() {
  const roots = [
    ...COMPONENT_DIRS.map((d) => join(FRONTEND_ROOT, "src", "components", d)),
    ...ROUTE_DIRS.map((d) => join(FRONTEND_ROOT, "src", d)),
  ];
  const files = new Set();
  for (const root of roots) {
    for (const f of collectSourceFiles(root)) files.add(f);
  }
  return [...files].sort();
}

/**
 * Flatten en.json into a set of leaf dot-paths (string values) and a set of
 * node dot-paths (every object prefix). A referenced key resolves if it is a
 * leaf, and a template prefix resolves if it is a node with children.
 */
function indexMessages(messages) {
  const leaves = new Set();
  const nodes = new Set();
  const walk = (obj, prefix) => {
    for (const [key, value] of Object.entries(obj)) {
      const path = prefix ? `${prefix}.${key}` : key;
      if (value !== null && typeof value === "object" && !Array.isArray(value)) {
        nodes.add(path);
        walk(value, path);
      } else {
        leaves.add(path);
      }
    }
  };
  walk(messages, "");
  return { leaves, nodes };
}

function lineOf(source, index) {
  return source.slice(0, index).split("\n").length;
}

// `const t = useTranslations("ns")` / `const t = await getTranslations("ns")`
// and the no-arg root form `useTranslations()`.
const NS_DECL = /(?:const|let|var)\s+(\w+)\s*=\s*(?:await\s+)?(?:useTranslations|getTranslations)\(\s*(?:(["'])([^"']*)\2)?\s*\)/g;

/** Map each translator variable name to the set of namespaces it may carry. */
function extractNamespaces(source) {
  const varToNs = new Map();
  let m;
  NS_DECL.lastIndex = 0;
  while ((m = NS_DECL.exec(source)) !== null) {
    const varName = m[1];
    const ns = m[3] ?? ""; // no-arg → root namespace
    const set = varToNs.get(varName) ?? new Set();
    set.add(ns);
    varToNs.set(varName, set);
  }
  return varToNs;
}

/** Extract `t("static")` and `t(`static.prefix.${x}`)` references for one var. */
function extractReferences(source, varName) {
  const refs = [];
  // static string arg: t("a.b") / t('a.b', {...})
  const staticRe = new RegExp(
    `(?<![\\w.])${varName}\\(\\s*(["'])([^"'\\n]+?)\\1`,
    "g"
  );
  let m;
  while ((m = staticRe.exec(source)) !== null) {
    refs.push({ kind: "static", key: m[2], index: m.index });
  }
  // template literal: capture the static prefix before the first ${
  const tmplRe = new RegExp(`(?<![\\w.])${varName}\\(\\s*\`([^\`]*?)\\$\\{`, "g");
  while ((m = tmplRe.exec(source)) !== null) {
    const prefix = m[1];
    if (prefix.length > 0) {
      refs.push({ kind: "prefix", key: prefix, index: m.index });
    }
  }
  return refs;
}

function joinKey(ns, key) {
  return ns ? `${ns}.${key}` : key;
}

/**
 * Run the audit.
 * @returns {{missing: Array, warnings: Array, scannedFiles: number, referenceCount: number}}
 */
export function runAudit() {
  const messages = JSON.parse(readFileSync(MESSAGES_PATH, "utf8"));
  const { leaves, nodes } = indexMessages(messages);
  const files = scanRoots();

  const missing = [];
  const warnings = [];
  let referenceCount = 0;

  for (const file of files) {
    const source = readFileSync(file, "utf8");
    const rel = file.slice(FRONTEND_ROOT.length + 1).replace(/\\/g, "/");
    const varToNs = extractNamespaces(source);

    for (const [varName, namespaces] of varToNs) {
      for (const ref of extractReferences(source, varName)) {
        referenceCount += 1;
        const candidates = [...namespaces];
        let resolved = false;
        if (ref.kind === "static") {
          resolved = candidates.some((ns) => {
            const full = joinKey(ns, ref.key);
            return leaves.has(full) || nodes.has(full);
          });
        } else {
          // prefix (template literal) — must be a node with children
          const prefix = ref.key.replace(/\.$/, "");
          resolved = candidates.some((ns) => {
            const full = joinKey(ns, prefix);
            return nodes.has(full);
          });
        }
        if (!resolved) {
          missing.push({
            file: rel,
            line: lineOf(source, ref.index),
            namespaces: candidates,
            kind: ref.kind,
            key: ref.key,
            resolvedAs: candidates.map((ns) => joinKey(ns, ref.key)),
          });
        }
      }
    }

    // Soft hardcoded-string heuristic (report only).
    collectHardcoded(source, rel, warnings);
  }

  return { missing, warnings, scannedFiles: files.length, referenceCount };
}

// Attributes that render user-facing copy (a plain-string value is suspicious).
const TEXT_ATTRS =
  /\b(?:title|label|placeholder|description|reason|alt|aria-label)\s*=\s*"([A-Za-z][^"]*?)"/g;
// JSX text: a capitalized multi-word run between tags, e.g. >Draft report<
const JSX_TEXT = />\s*([A-Z][a-z]+(?:\s+[A-Za-z]+){1,})\s*</g;

function collectHardcoded(source, rel, warnings) {
  let m;
  TEXT_ATTRS.lastIndex = 0;
  while ((m = TEXT_ATTRS.exec(source)) !== null) {
    const text = m[1].trim();
    if (!/\s/.test(text)) continue; // single token — likely token/id, skip
    warnings.push({ file: rel, line: lineOf(source, m.index), kind: "attr", text });
  }
  JSX_TEXT.lastIndex = 0;
  while ((m = JSX_TEXT.exec(source)) !== null) {
    const text = m[1].trim();
    warnings.push({ file: rel, line: lineOf(source, m.index), kind: "jsx", text });
  }
}

// CLI entry (cross-platform: compare resolved paths, not URL string forms).
const invokedPath = process.argv[1] ? resolve(process.argv[1]) : "";
const selfPath = fileURLToPath(import.meta.url);
if (invokedPath === selfPath) {
  const { missing, warnings, scannedFiles, referenceCount } = runAudit();
  console.log(
    `i18n-audit: scanned ${scannedFiles} files, ${referenceCount} key references.`
  );
  if (warnings.length > 0) {
    console.log(`\n${warnings.length} suspected hardcoded string(s) (soft):`);
    for (const w of warnings) {
      console.log(`  [${w.kind}] ${w.file}:${w.line}  "${w.text}"`);
    }
  } else {
    console.log("No suspected hardcoded strings.");
  }
  if (missing.length > 0) {
    console.error(`\n${missing.length} MISSING i18n key(s):`);
    for (const miss of missing) {
      console.error(
        `  ${miss.file}:${miss.line}  ${miss.kind} "${miss.key}"  (tried: ${miss.resolvedAs.join(", ")})`
      );
    }
    process.exit(1);
  }
  console.log("\nAll referenced i18n keys resolve. ✔");
}
