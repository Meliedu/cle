# Plan A: Capacitor Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Capacitor-based iOS + Android app that wraps the existing Next.js production web app, supports Clerk OAuth via deep-link callback, and reaches TestFlight (iOS) + Play Internal Testing (Android) with correct icons, splash, privacy manifest.

**Architecture:** A new `mobile/` workspace (sibling of `frontend/` and `backend/`) holds Capacitor 6 + iOS (Swift) + Android (Kotlin) projects. Capacitor's `server.url` points at the production Next.js URL so the WebView always loads the latest deploy. Clerk's hosted UI runs inside the WebView; "Continue with Google" opens a Capacitor Browser SFSafariViewController/Custom Tab and returns via custom URL scheme `meli://clerk-callback`.

**Tech Stack:** Capacitor 6, Node 20, Xcode 15+, Android Studio Hedgehog+, Swift 5.9, Kotlin 1.9, Gradle 8, fastlane, GitHub Actions (macOS + Ubuntu runners).

**Spec reference:** `docs/superpowers/specs/2026-04-26-mobile-app-design.md` §2, §3, §4, §5, §6.3, §8.

**Open questions resolved before starting (block on these):**
- Production domain URL (placeholder used in plan: `https://meli.app` — replace with real value at Task A2 if different).
- Apple Developer enrollment status (individual or HKUST org).
- Android keystore generated and stored in 1Password / vault.

---

## File Structure

```
cle/
└── mobile/                                 NEW workspace
    ├── package.json                        Capacitor CLI + scripts
    ├── package-lock.json
    ├── capacitor.config.ts                 Hosted-mode WebView config
    ├── tsconfig.json
    ├── .gitignore
    ├── .env.example
    ├── README.md                           Build/run/release instructions
    ├── public/                             Required by Capacitor (unused in hosted mode)
    │   └── index.html                      Stub
    ├── shared/
    │   ├── tokens.json                     Generated from frontend/src/styles/tokens.css
    │   └── types.ts                        Shared TS types for plugin params/results
    ├── scripts/
    │   ├── extract-tokens.mjs              tokens.css → tokens.json
    │   ├── codegen-tokens.mjs              tokens.json → ios+android constants
    │   └── verify-tokens-fresh.mjs         CI guard against stale codegen
    ├── ios/
    │   ├── App/App/Info.plist              Permissions strings, URL scheme
    │   ├── App/App/PrivacyInfo.xcprivacy   Apple privacy manifest
    │   ├── App/App/Assets.xcassets/        Icons + splash
    │   ├── App/App/AppDelegate.swift       Custom URL scheme handler
    │   ├── App/App/Plugins/                (empty for Plan A; D and E add plugins)
    │   ├── App/Podfile
    │   └── fastlane/
    │       ├── Appfile
    │       ├── Fastfile                    build_and_upload lane
    │       └── Matchfile
    └── android/
        ├── app/build.gradle                appId, versionCode/Name, signingConfig
        ├── app/src/main/AndroidManifest.xml URL scheme intent filter, permissions
        ├── app/src/main/res/               Icons + splash + colors
        ├── app/src/main/java/.../MainActivity.kt URL scheme handler
        ├── app/src/main/java/.../plugins/  (empty for Plan A)
        └── app/google-services.json        FCM config (gitignored, env-injected)

cle/.github/workflows/
├── mobile-ios.yml                          Tag-triggered TestFlight build
└── mobile-android.yml                      Tag-triggered Play Internal upload

cle/frontend/src/lib/
└── capacitor.ts                            isNative() helper used app-wide

cle/frontend/src/styles/
└── tokens.css                              (existing — no changes; just becomes codegen input)
```

---

## Task A1: Workspace scaffold and Capacitor init

**Files:**
- Create: `mobile/package.json`
- Create: `mobile/tsconfig.json`
- Create: `mobile/.gitignore`
- Create: `mobile/.env.example`
- Create: `mobile/README.md`
- Create: `mobile/public/index.html`
- Modify: `.gitignore` (root)

- [ ] **Step 1: Create the `mobile/` directory and `package.json`**

```bash
mkdir -p /home/badur/projects/cle/mobile
cd /home/badur/projects/cle/mobile
```

Write `mobile/package.json`:

```json
{
  "name": "meli-mobile",
  "version": "0.1.0",
  "private": true,
  "description": "Meli iOS + Android app (Capacitor wrapper of the Next.js web app)",
  "scripts": {
    "tokens:extract": "node scripts/extract-tokens.mjs",
    "tokens:codegen": "node scripts/codegen-tokens.mjs",
    "tokens:verify": "node scripts/verify-tokens-fresh.mjs",
    "tokens:all": "npm run tokens:extract && npm run tokens:codegen",
    "cap:sync": "npm run tokens:all && cap sync",
    "ios:open": "cap open ios",
    "android:open": "cap open android",
    "ios:run": "npm run cap:sync && cap run ios",
    "android:run": "npm run cap:sync && cap run android"
  },
  "dependencies": {
    "@capacitor/android": "^6.1.0",
    "@capacitor/app": "^6.0.1",
    "@capacitor/browser": "^6.0.2",
    "@capacitor/core": "^6.1.0",
    "@capacitor/haptics": "^6.0.1",
    "@capacitor/ios": "^6.1.0",
    "@capacitor/keyboard": "^6.0.2",
    "@capacitor/splash-screen": "^6.0.2",
    "@capacitor/status-bar": "^6.0.1"
  },
  "devDependencies": {
    "@capacitor/cli": "^6.1.0",
    "typescript": "^5.5.0"
  }
}
```

- [ ] **Step 2: Add `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "lib": ["ES2022", "DOM"]
  },
  "include": ["shared/**/*.ts", "scripts/**/*.mjs"]
}
```

- [ ] **Step 3: Add `.gitignore`**

```gitignore
node_modules/
ios/App/App/Pods/
ios/App/App.xcworkspace/xcuserdata/
ios/App/App.xcodeproj/xcuserdata/
ios/App/App.xcodeproj/project.xcworkspace/xcuserdata/
ios/App/Podfile.lock
android/app/build/
android/build/
android/.gradle/
android/local.properties
android/app/release/
android/app/google-services.json
*.keystore
*.p8
*.p12
*.mobileprovision
.env
.env.local
shared/tokens.json
ios/App/App/Tokens.swift
android/app/src/main/java/hk/ust/meli/Tokens.kt
```

- [ ] **Step 4: Add `.env.example`**

```bash
# Production WebView URL — what the Capacitor server.url points at
MELI_PROD_URL=https://meli.app

# Apple Developer signing (used by fastlane)
APPLE_TEAM_ID=
APP_STORE_CONNECT_KEY_ID=
APP_STORE_CONNECT_ISSUER_ID=
APP_STORE_CONNECT_KEY_FILE=

# Match (fastlane signing certs)
MATCH_PASSWORD=
MATCH_GIT_URL=

# Android signing
ANDROID_KEYSTORE_PATH=
ANDROID_KEYSTORE_PASSWORD=
ANDROID_KEY_ALIAS=
ANDROID_KEY_PASSWORD=

# Firebase (for FCM token issuance — used by Android push wiring in Plan C)
FIREBASE_PROJECT_ID=
```

- [ ] **Step 5: Add `mobile/README.md` with build/run instructions**

```markdown
# Meli Mobile

iOS + Android app for Meli, built with Capacitor 6. Wraps the production Next.js web app and adds native pronunciation + flashcard screens (added in Plans D and E).

## Local development

Prerequisites:
- Node 20+
- Xcode 15+ (macOS only, for iOS)
- Android Studio Hedgehog+ with SDK 34
- Cocoapods 1.15+
- Java 17

```bash
cd mobile
cp .env.example .env  # fill in values
npm install
npm run cap:sync
npm run ios:open      # opens Xcode
npm run android:open  # opens Android Studio
```

## Architecture

The app is a thin native shell that loads the production Next.js app
in a WebView. See `docs/superpowers/specs/2026-04-26-mobile-app-design.md`
for the full design.

## Releases

Tag pushes (`mobile-v0.1.0`) trigger GitHub Actions to build and upload:
- iOS → TestFlight (internal track)
- Android → Play Console (internal testing track)
```

- [ ] **Step 6: Add stub `public/index.html`**

Capacitor's CLI requires a `webDir` even in hosted mode. We point it at `public/` and put a stub there.

```html
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Meli</title></head>
<body><script>window.location.href = "https://meli.app";</script></body>
</html>
```

- [ ] **Step 7: Update root `.gitignore`** to ignore mobile build outputs from the workspace root

Append to `/home/badur/projects/cle/.gitignore`:

```gitignore

# mobile workspace
mobile/node_modules/
mobile/ios/App/App/Pods/
mobile/ios/App/Podfile.lock
mobile/android/app/build/
mobile/android/build/
mobile/android/.gradle/
mobile/android/app/google-services.json
mobile/.env
```

- [ ] **Step 8: Install dependencies and verify**

Run:
```bash
cd mobile && npm install
```

Expected: clean install, `node_modules/` populated, no errors.

- [ ] **Step 9: Commit**

```bash
git add mobile/ .gitignore
git commit -m "feat(mobile): scaffold Capacitor workspace"
```

---

## Task A2: Capacitor config and platform projects

**Files:**
- Create: `mobile/capacitor.config.ts`

- [ ] **Step 1: Write `mobile/capacitor.config.ts`**

```ts
import type { CapacitorConfig } from '@capacitor/cli';

const PROD_URL = process.env.MELI_PROD_URL ?? 'https://meli.app';

const config: CapacitorConfig = {
  appId: 'hk.ust.meli',
  appName: 'Meli',
  webDir: 'public',
  server: {
    url: PROD_URL,
    cleartext: false,
    androidScheme: 'https',
    iosScheme: 'https',
    allowNavigation: [
      '*.clerk.accounts.dev',
      '*.clerk.com',
      'accounts.google.com'
    ]
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 1200,
      backgroundColor: '#FAF7EE',
      androidScaleType: 'CENTER_CROP'
    }
  },
  ios: {
    contentInset: 'always'
  },
  android: {
    allowMixedContent: false
  }
};

export default config;
```

- [ ] **Step 2: Add iOS platform**

```bash
cd mobile
npx cap add ios
```

Expected: `mobile/ios/` populated with Xcode project, Podfile, etc.

- [ ] **Step 3: Add Android platform**

```bash
npx cap add android
```

Expected: `mobile/android/` populated with Gradle project, manifest, etc.

- [ ] **Step 4: First sync**

```bash
npx cap sync
```

Expected: native projects updated to match `capacitor.config.ts`. No errors.

- [ ] **Step 5: Verify iOS opens**

```bash
npm run ios:open
```

Expected: Xcode opens with the `App.xcworkspace` project, no red errors. Close Xcode.

- [ ] **Step 6: Verify Android opens**

```bash
npm run android:open
```

Expected: Android Studio opens, Gradle sync completes, no errors. Close Android Studio.

- [ ] **Step 7: Commit**

```bash
git add mobile/
git commit -m "feat(mobile): add iOS and Android platforms"
```

---

## Task A3: Token codegen pipeline

**Files:**
- Create: `mobile/scripts/extract-tokens.mjs`
- Create: `mobile/scripts/codegen-tokens.mjs`
- Create: `mobile/scripts/verify-tokens-fresh.mjs`
- Create: `mobile/shared/tokens.json` (generated; commit the first generation so CI has a baseline)

- [ ] **Step 1: Write `extract-tokens.mjs`**

Reads the existing CSS file and converts `oklch(...)` colors to JSON:

```js
#!/usr/bin/env node
// Extract design tokens from frontend/src/styles/tokens.css → mobile/shared/tokens.json
import fs from 'node:fs';
import path from 'node:path';

const CSS_PATH = path.resolve('../frontend/src/styles/tokens.css');
const OUT_PATH = path.resolve('shared/tokens.json');

const css = fs.readFileSync(CSS_PATH, 'utf8');

// Match `--name: value;` inside `:root { ... }` only.
const rootBlock = css.match(/:root\s*{([^}]*)}/s)?.[1] ?? '';
const tokens = {};
for (const line of rootBlock.split(/\n/)) {
  const m = line.match(/^\s*--([a-zA-Z0-9-]+)\s*:\s*([^;]+);/);
  if (!m) continue;
  const [, name, raw] = m;
  tokens[name] = raw.trim();
}

if (Object.keys(tokens).length === 0) {
  console.error('No tokens extracted — is tokens.css empty or missing :root?');
  process.exit(1);
}

fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
fs.writeFileSync(OUT_PATH, JSON.stringify(tokens, null, 2) + '\n');
console.log(`Wrote ${Object.keys(tokens).length} tokens → ${OUT_PATH}`);
```

- [ ] **Step 2: Write `codegen-tokens.mjs`**

Generates Swift + Kotlin constant files from `tokens.json`:

```js
#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const TOKENS = JSON.parse(fs.readFileSync('shared/tokens.json', 'utf8'));

// We only codegen color tokens for native. Typography and spacing stay web-only
// (native uses platform metrics).
const isColor = (val) =>
  val.startsWith('oklch(') || val.startsWith('#') || val.startsWith('rgb(');

const colorTokens = Object.entries(TOKENS).filter(([, v]) => isColor(v));

// --- Swift ---
const swiftLines = [
  '// AUTO-GENERATED — DO NOT EDIT. Run `npm run tokens:codegen` in mobile/.',
  'import UIKit',
  '',
  'enum Tokens {',
  ...colorTokens.map(([name, value]) => {
    const swiftName = toCamel(name);
    return `  static let ${swiftName} = UIColor(hex: ${JSON.stringify(value)})`;
  }),
  '}',
  '',
  'extension UIColor {',
  '  convenience init(hex: String) {',
  '    // Tolerates "#rrggbb", "#rrggbbaa", and "oklch(...)" by parsing CSS color',
  '    // via a small lookup. Real conversion is delegated to a runtime helper.',
  '    let parsed = TokenColorParser.parse(hex)',
  '    self.init(red: parsed.r, green: parsed.g, blue: parsed.b, alpha: parsed.a)',
  '  }',
  '}',
  ''
];
fs.writeFileSync('ios/App/App/Tokens.swift', swiftLines.join('\n'));

// --- Kotlin ---
const kotlinLines = [
  '// AUTO-GENERATED — DO NOT EDIT. Run `npm run tokens:codegen` in mobile/.',
  'package hk.ust.meli',
  '',
  'import androidx.compose.ui.graphics.Color',
  '',
  'object Tokens {',
  ...colorTokens.map(([name, value]) => {
    const kName = toCamel(name);
    return `  val ${kName}: Color = TokenColorParser.parse(${JSON.stringify(value)})`;
  }),
  '}',
  ''
];
fs.writeFileSync('android/app/src/main/java/hk/ust/meli/Tokens.kt', kotlinLines.join('\n'));

console.log(`Wrote ${colorTokens.length} color tokens to Swift + Kotlin`);

function toCamel(kebab) {
  return kebab.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}
```

- [ ] **Step 3: Write `verify-tokens-fresh.mjs`** (CI guard)

```js
#!/usr/bin/env node
// CI guard: re-run extract+codegen, compare to checked-in files.
// Fails build if Swift/Kotlin token files are stale relative to tokens.css.
import { execSync } from 'node:child_process';
import fs from 'node:fs';

const before = {
  json: read('shared/tokens.json'),
  swift: read('ios/App/App/Tokens.swift'),
  kotlin: read('android/app/src/main/java/hk/ust/meli/Tokens.kt'),
};

execSync('node scripts/extract-tokens.mjs', { stdio: 'inherit' });
execSync('node scripts/codegen-tokens.mjs', { stdio: 'inherit' });

const after = {
  json: read('shared/tokens.json'),
  swift: read('ios/App/App/Tokens.swift'),
  kotlin: read('android/app/src/main/java/hk/ust/meli/Tokens.kt'),
};

const stale = Object.keys(before).filter(k => before[k] !== after[k]);
if (stale.length) {
  console.error(`Stale token files: ${stale.join(', ')}`);
  console.error(`Run \`npm run tokens:all\` in mobile/ and commit the result.`);
  process.exit(1);
}
console.log('Tokens up-to-date.');

function read(p) { try { return fs.readFileSync(p, 'utf8'); } catch { return ''; } }
```

- [ ] **Step 4: Create native helper files for color parsing** (referenced by codegen)

Create `mobile/ios/App/App/TokenColorParser.swift`:

```swift
import UIKit

/// Parses CSS color values used by tokens.css into RGBA components.
/// Supports: `oklch(<L> <C> <H>)` (with optional alpha), `#RRGGBB`, `#RRGGBBAA`.
enum TokenColorParser {
    struct RGBA { let r: CGFloat; let g: CGFloat; let b: CGFloat; let a: CGFloat }

    static func parse(_ raw: String) -> RGBA {
        let s = raw.trimmingCharacters(in: .whitespaces).lowercased()
        if s.hasPrefix("#") { return parseHex(s) }
        if s.hasPrefix("oklch") { return parseOklch(s) }
        return RGBA(r: 0, g: 0, b: 0, a: 1)
    }

    private static func parseHex(_ s: String) -> RGBA {
        let hex = String(s.dropFirst())
        let len = hex.count
        guard len == 6 || len == 8 else { return RGBA(r: 0, g: 0, b: 0, a: 1) }
        let n = UInt64(hex, radix: 16) ?? 0
        if len == 6 {
            return RGBA(
                r: CGFloat((n >> 16) & 0xff) / 255,
                g: CGFloat((n >> 8) & 0xff) / 255,
                b: CGFloat(n & 0xff) / 255,
                a: 1
            )
        }
        return RGBA(
            r: CGFloat((n >> 24) & 0xff) / 255,
            g: CGFloat((n >> 16) & 0xff) / 255,
            b: CGFloat((n >> 8) & 0xff) / 255,
            a: CGFloat(n & 0xff) / 255
        )
    }

    private static func parseOklch(_ s: String) -> RGBA {
        // Strip `oklch(` and `)`, split, convert to sRGB.
        let inside = s
            .replacingOccurrences(of: "oklch(", with: "")
            .replacingOccurrences(of: ")", with: "")
            .replacingOccurrences(of: ",", with: " ")
        let parts = inside.split(separator: " ").map { String($0) }
        guard parts.count >= 3 else { return RGBA(r: 0, g: 0, b: 0, a: 1) }
        let l = pct(parts[0])
        let c = Double(parts[1]) ?? 0
        let h = Double(parts[2]) ?? 0
        let a: CGFloat = parts.count >= 4 ? CGFloat(pct(parts[3])) : 1
        let (r, g, b) = OklchToSRGB.convert(l: l, c: c, h: h)
        return RGBA(r: CGFloat(r), g: CGFloat(g), b: CGFloat(b), a: a)
    }

    private static func pct(_ raw: String) -> Double {
        if raw.hasSuffix("%") {
            return (Double(raw.dropLast()) ?? 0) / 100
        }
        return Double(raw) ?? 0
    }
}

enum OklchToSRGB {
    /// Reference conversion oklch → linear-sRGB → sRGB. Adapted from
    /// https://www.w3.org/TR/css-color-4/#color-conversion-code (public domain).
    static func convert(l: Double, c: Double, h: Double) -> (Double, Double, Double) {
        let hRad = h * .pi / 180
        let a = c * cos(hRad)
        let b = c * sin(hRad)
        // Oklab → linear sRGB
        let lLin = pow(l + 0.3963377774 * a + 0.2158037573 * b, 3)
        let mLin = pow(l - 0.1055613458 * a - 0.0638541728 * b, 3)
        let sLin = pow(l - 0.0894841775 * a - 1.2914855480 * b, 3)
        let r =  4.0767416621 * lLin - 3.3077115913 * mLin + 0.2309699292 * sLin
        let g = -1.2684380046 * lLin + 2.6097574011 * mLin - 0.3413193965 * sLin
        let bb = -0.0041960863 * lLin - 0.7034186147 * mLin + 1.7076147010 * sLin
        return (clamp(srgbEncode(r)), clamp(srgbEncode(g)), clamp(srgbEncode(bb)))
    }
    private static func srgbEncode(_ v: Double) -> Double {
        v <= 0.0031308 ? 12.92 * v : 1.055 * pow(v, 1.0/2.4) - 0.055
    }
    private static func clamp(_ v: Double) -> Double { max(0, min(1, v)) }
}
```

Create `mobile/android/app/src/main/java/hk/ust/meli/TokenColorParser.kt`:

```kotlin
package hk.ust.meli

import androidx.compose.ui.graphics.Color
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sin

/** Parses CSS color values from tokens.css. Supports oklch(...) and hex. */
object TokenColorParser {
    fun parse(raw: String): Color {
        val s = raw.trim().lowercase()
        return when {
            s.startsWith("#") -> parseHex(s)
            s.startsWith("oklch") -> parseOklch(s)
            else -> Color.Black
        }
    }

    private fun parseHex(s: String): Color {
        val hex = s.removePrefix("#")
        return when (hex.length) {
            6 -> {
                val n = hex.toLong(16)
                Color(((n shr 16) and 0xff) / 255f, ((n shr 8) and 0xff) / 255f, (n and 0xff) / 255f, 1f)
            }
            8 -> {
                val n = hex.toLong(16)
                Color(
                    ((n shr 24) and 0xff) / 255f,
                    ((n shr 16) and 0xff) / 255f,
                    ((n shr 8) and 0xff) / 255f,
                    (n and 0xff) / 255f
                )
            }
            else -> Color.Black
        }
    }

    private fun parseOklch(s: String): Color {
        val inside = s.removePrefix("oklch(").removeSuffix(")").replace(",", " ")
        val parts = inside.split(Regex("\\s+")).filter { it.isNotEmpty() }
        if (parts.size < 3) return Color.Black
        val l = pct(parts[0])
        val c = parts[1].toDoubleOrNull() ?: 0.0
        val h = parts[2].toDoubleOrNull() ?: 0.0
        val a = if (parts.size >= 4) pct(parts[3]).toFloat() else 1f
        val (r, g, b) = oklchToSRGB(l, c, h)
        return Color(r.toFloat(), g.toFloat(), b.toFloat(), a)
    }

    private fun pct(raw: String): Double =
        if (raw.endsWith("%")) (raw.removeSuffix("%").toDoubleOrNull() ?: 0.0) / 100.0
        else raw.toDoubleOrNull() ?: 0.0

    private fun oklchToSRGB(l: Double, c: Double, h: Double): Triple<Double, Double, Double> {
        val hRad = h * Math.PI / 180.0
        val a = c * cos(hRad)
        val b = c * sin(hRad)
        val lLin = (l + 0.3963377774 * a + 0.2158037573 * b).pow(3)
        val mLin = (l - 0.1055613458 * a - 0.0638541728 * b).pow(3)
        val sLin = (l - 0.0894841775 * a - 1.2914855480 * b).pow(3)
        val r = 4.0767416621 * lLin - 3.3077115913 * mLin + 0.2309699292 * sLin
        val g = -1.2684380046 * lLin + 2.6097574011 * mLin - 0.3413193965 * sLin
        val bb = -0.0041960863 * lLin - 0.7034186147 * mLin + 1.7076147010 * sLin
        return Triple(clamp(srgb(r)), clamp(srgb(g)), clamp(srgb(bb)))
    }
    private fun srgb(v: Double) =
        if (v <= 0.0031308) 12.92 * v else 1.055 * v.pow(1.0 / 2.4) - 0.055
    private fun clamp(v: Double) = v.coerceIn(0.0, 1.0)
}
```

- [ ] **Step 5: Run extract + codegen and verify output**

```bash
cd mobile
npm run tokens:extract
npm run tokens:codegen
```

Expected:
- `mobile/shared/tokens.json` exists with extracted CSS variables
- `mobile/ios/App/App/Tokens.swift` exists with `Tokens.<name>` UIColor constants
- `mobile/android/app/src/main/java/hk/ust/meli/Tokens.kt` exists with `Tokens.<name>` Color constants

- [ ] **Step 6: Run verify in clean state — should pass**

```bash
npm run tokens:verify
```

Expected: `Tokens up-to-date.` — exit 0.

- [ ] **Step 7: Commit**

```bash
git add mobile/scripts mobile/shared/tokens.json mobile/ios/App/App/TokenColorParser.swift mobile/ios/App/App/Tokens.swift mobile/android/app/src/main/java/hk/ust/meli/TokenColorParser.kt mobile/android/app/src/main/java/hk/ust/meli/Tokens.kt
git commit -m "feat(mobile): tokens codegen from frontend tokens.css → Swift + Kotlin"
```

---

## Task A4: Custom URL scheme (iOS)

**Files:**
- Modify: `mobile/ios/App/App/Info.plist`
- Modify: `mobile/ios/App/App/AppDelegate.swift`

- [ ] **Step 1: Add `meli://` URL scheme to `Info.plist`**

Open `mobile/ios/App/App/Info.plist` and add to the top-level `<dict>`:

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLName</key>
        <string>hk.ust.meli</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>meli</string>
        </array>
    </dict>
</array>
```

- [ ] **Step 2: Add `NSMicrophoneUsageDescription` and `NSCameraUsageDescription`**

Same `Info.plist`, in the same top-level `<dict>`:

```xml
<key>NSMicrophoneUsageDescription</key>
<string>Meli uses the microphone to score your pronunciation practice.</string>
<key>NSCameraUsageDescription</key>
<string>Meli uses the camera to scan documents you upload to your courses.</string>
```

- [ ] **Step 3: Wire `AppDelegate.swift` to forward URL opens to Capacitor**

`mobile/ios/App/App/AppDelegate.swift` should already have the Capacitor `application(_:open:options:)` from `cap add ios`. Confirm it includes:

```swift
func application(_ app: UIApplication, open url: URL, options: [UIApplication.OpenURLOptionsKey : Any] = [:]) -> Bool {
    return ApplicationDelegateProxy.shared.application(app, open: url, options: options)
}
```

If missing, add it.

- [ ] **Step 4: Build and verify scheme on simulator**

```bash
cd mobile
npx cap sync ios
npm run ios:open
```

In Xcode: Product → Run (⌘R) on iOS simulator. Once running, in a separate terminal:

```bash
xcrun simctl openurl booted "meli://test"
```

Expected: app comes to foreground (the URL itself doesn't navigate yet — that wires up in Plan C — but the OS routing must work).

- [ ] **Step 5: Commit**

```bash
git add mobile/ios/
git commit -m "feat(mobile-ios): register meli:// URL scheme + permission strings"
```

---

## Task A5: Custom URL scheme (Android)

**Files:**
- Modify: `mobile/android/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Add `meli://` intent filter**

Open `mobile/android/app/src/main/AndroidManifest.xml`, find the `<activity android:name=".MainActivity" ...>` block, and add inside it:

```xml
<intent-filter android:autoVerify="false">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="meli" />
</intent-filter>
```

- [ ] **Step 2: Add required permissions**

In the same manifest, inside `<manifest>` but outside `<application>`:

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.RECORD_AUDIO" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
<uses-permission android:name="android.permission.VIBRATE" />
```

Some of these are already there from Capacitor's defaults — leave duplicates out.

- [ ] **Step 3: Build and verify**

```bash
cd mobile
npx cap sync android
npm run android:open
```

In Android Studio: Run on an emulator. Once running:

```bash
adb shell am start -W -a android.intent.action.VIEW -d "meli://test" hk.ust.meli
```

Expected: emulator brings the app to foreground.

- [ ] **Step 4: Commit**

```bash
git add mobile/android/
git commit -m "feat(mobile-android): register meli:// intent filter + permissions"
```

---

## Task A6: `isNative()` helper in frontend

**Files:**
- Create: `frontend/src/lib/capacitor.ts`
- Test: `frontend/src/lib/capacitor.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/capacitor.test.ts`:

```ts
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { isNative, getPlatform } from './capacitor';

describe('capacitor helpers', () => {
  const originalNavigator = globalThis.navigator;

  afterEach(() => {
    Object.defineProperty(globalThis, 'navigator', {
      value: originalNavigator, writable: true, configurable: true,
    });
    delete (globalThis as any).Capacitor;
  });

  it('returns false outside Capacitor', () => {
    expect(isNative()).toBe(false);
  });

  it('returns true when Capacitor.isNativePlatform() is true', () => {
    (globalThis as any).Capacitor = { isNativePlatform: () => true, getPlatform: () => 'ios' };
    expect(isNative()).toBe(true);
  });

  it('reports platform from Capacitor.getPlatform()', () => {
    (globalThis as any).Capacitor = { isNativePlatform: () => true, getPlatform: () => 'android' };
    expect(getPlatform()).toBe('android');
  });

  it('reports "web" outside Capacitor', () => {
    expect(getPlatform()).toBe('web');
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd frontend
npm test -- src/lib/capacitor.test.ts
```

Expected: FAIL — `Cannot find module './capacitor'` or similar.

- [ ] **Step 3: Implement `frontend/src/lib/capacitor.ts`**

```ts
/**
 * Tiny helpers for detecting whether the Next.js app is running inside the
 * Capacitor WebView. The Capacitor runtime injects a global `Capacitor` object
 * with `isNativePlatform()` and `getPlatform()` methods.
 */

type Platform = 'ios' | 'android' | 'web';

interface CapacitorGlobal {
  isNativePlatform: () => boolean;
  getPlatform: () => Platform | string;
}

function getCapacitor(): CapacitorGlobal | undefined {
  return (globalThis as { Capacitor?: CapacitorGlobal }).Capacitor;
}

export function isNative(): boolean {
  return getCapacitor()?.isNativePlatform() ?? false;
}

export function getPlatform(): Platform {
  const raw = getCapacitor()?.getPlatform() ?? 'web';
  return raw === 'ios' || raw === 'android' ? raw : 'web';
}
```

- [ ] **Step 4: Re-run tests**

```bash
npm test -- src/lib/capacitor.test.ts
```

Expected: PASS — 4/4 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/capacitor.ts frontend/src/lib/capacitor.test.ts
git commit -m "feat(frontend): isNative + getPlatform helpers for Capacitor detection"
```

---

## Task A7: Clerk OAuth deep-link callback (iOS + Android)

This task is the OAuth wrinkle from spec §5.2. When a student taps "Continue with Google" inside the WebView, the WebView is forbidden by Google's policy. We open the system browser via Capacitor's Browser plugin, let Google + Clerk complete the flow, and Clerk redirects to `meli://clerk-callback?...` which we forward back to the WebView.

**Files:**
- Create: `mobile/shared/types.ts`
- Modify: `mobile/ios/App/App/AppDelegate.swift`
- Modify: `mobile/android/app/src/main/java/hk/ust/meli/MainActivity.kt`
- Create: `frontend/src/lib/clerk-mobile-oauth.ts`
- Modify: `frontend/src/app/sign-in/[[...sign-in]]/page.tsx` (or wherever the sign-in page lives — see Step 0)
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 0: Locate the existing Clerk sign-in page**

```bash
find frontend/src/app/sign-in -type f
```

Expected: a page.tsx file. If no path matches, the sign-in is using Clerk's `<SignIn>` component embedded in `app/sign-in/page.tsx`. Note the exact path for Step 4.

- [ ] **Step 1: Add `mobile/shared/types.ts`** with the OAuth-callback message shape

```ts
/** Messages exchanged between native shell and WebView. */

export type ClerkOAuthCallback = {
  kind: 'clerk-oauth-callback';
  /** Full URL the OS handed us — e.g. `meli://clerk-callback?token=...&...` */
  url: string;
};

export type NativeToWeb = ClerkOAuthCallback;
```

- [ ] **Step 2: Forward `meli://clerk-callback` URLs to the WebView (iOS)**

The Capacitor `App` plugin already emits an `appUrlOpen` event for any URL hitting our scheme. We don't need extra Swift code beyond what `cap add ios` produced — confirm by reading `AppDelegate.swift` for the `application(_:open:)` proxy. If absent, add it as in Task A4.

Capacitor will fire the `appUrlOpen` JS event automatically. The WebView-side handler (Step 5) consumes it.

- [ ] **Step 3: Forward `meli://clerk-callback` URLs to the WebView (Android)**

Read `mobile/android/app/src/main/java/hk/ust/meli/MainActivity.kt`. It should extend `BridgeActivity` (Capacitor's default). Capacitor automatically forwards URL intents to `appUrlOpen` — no Kotlin changes needed beyond the manifest edit in A5.

- [ ] **Step 4: Update sign-in page to use Capacitor Browser for social OAuth when isNative()**

Modify the sign-in page (path from Step 0; assume `frontend/src/app/sign-in/page.tsx` for the snippets below):

```tsx
'use client';
import { SignIn } from '@clerk/nextjs';
import { useEffect } from 'react';
import { isNative } from '@/lib/capacitor';
import { startMobileOAuth, listenForOAuthCallback } from '@/lib/clerk-mobile-oauth';

export default function SignInPage() {
  useEffect(() => {
    if (!isNative()) return;
    const stop = listenForOAuthCallback();
    return stop;
  }, []);

  if (isNative()) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6">
        <h1 className="text-2xl font-semibold">Sign in to Meli</h1>
        <button
          className="rounded-md bg-primary px-4 py-2 text-primary-foreground"
          onClick={() => startMobileOAuth('oauth_google')}
        >
          Continue with Google
        </button>
        <a className="text-sm underline" href="/sign-in/email">
          Or use email and password
        </a>
      </div>
    );
  }

  return <SignIn />;
}
```

- [ ] **Step 5: Implement `frontend/src/lib/clerk-mobile-oauth.ts`**

```ts
'use client';
import { useClerk } from '@clerk/nextjs';
import { isNative } from '@/lib/capacitor';

const REDIRECT_URL = 'meli://clerk-callback';

/**
 * Begins a social-OAuth flow on mobile by opening the system browser
 * (SFSafariViewController / Custom Tab via Capacitor Browser plugin).
 * Clerk completes OAuth and redirects to `meli://clerk-callback?...`
 * which the OS routes back to our app; `listenForOAuthCallback`
 * catches it.
 */
export async function startMobileOAuth(strategy: 'oauth_google' | 'oauth_apple') {
  if (!isNative()) {
    throw new Error('startMobileOAuth called on web — use SignIn component instead');
  }
  const { Browser } = await import('@capacitor/browser');
  // Clerk supports building the auth URL via signIn.authenticateWithRedirect
  // when running outside React; we use the lower-level URL builder here.
  const url = buildClerkAuthUrl(strategy);
  await Browser.open({ url, presentationStyle: 'popover' });
}

/**
 * Subscribes to Capacitor's appUrlOpen event and forwards Clerk
 * callback URLs to the Clerk client to complete sign-in.
 * Returns an unsubscribe function.
 */
export function listenForOAuthCallback(): () => void {
  let removed = false;
  let removeListener: (() => void) | null = null;
  (async () => {
    const { App } = await import('@capacitor/app');
    const { Browser } = await import('@capacitor/browser');
    const handle = await App.addListener('appUrlOpen', async ({ url }) => {
      if (!url.startsWith('meli://clerk-callback')) return;
      await Browser.close();
      // Hand the URL to Clerk; clerk.handleRedirectCallback expects a search-string-style URL.
      const callbackUrl = url.replace('meli://clerk-callback', window.location.origin + '/sso-callback');
      window.location.href = callbackUrl;
    });
    if (removed) {
      handle.remove();
    } else {
      removeListener = () => handle.remove();
    }
  })();
  return () => {
    removed = true;
    removeListener?.();
  };
}

function buildClerkAuthUrl(strategy: string): string {
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY!;
  const accountsHost = inferClerkHost(publishableKey);
  const params = new URLSearchParams({
    strategy,
    redirect_url: REDIRECT_URL,
    redirect_url_complete: REDIRECT_URL,
  });
  return `https://${accountsHost}/oauth/authorize?${params.toString()}`;
}

function inferClerkHost(publishableKey: string): string {
  // Clerk publishable keys are base64-encoded "host$key" — decode the host.
  const body = publishableKey.replace(/^pk_(test|live)_/, '');
  try {
    const decoded = atob(body);
    const [host] = decoded.split('$');
    return host;
  } catch {
    return 'clerk.accounts.dev';
  }
}
```

- [ ] **Step 6: Add `/sso-callback` Next.js route to complete Clerk sign-in**

Create `frontend/src/app/sso-callback/page.tsx`:

```tsx
'use client';
import { AuthenticateWithRedirectCallback } from '@clerk/nextjs';

export default function SsoCallbackPage() {
  return <AuthenticateWithRedirectCallback />;
}
```

- [ ] **Step 7: Add `meli://clerk-callback` to Clerk allowed redirects**

In Clerk dashboard (or via Clerk Backend API):

```bash
curl -X POST https://api.clerk.com/v1/instance/redirect_urls \
  -H "Authorization: Bearer $CLERK_SECRET_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "meli://clerk-callback"}'
```

Verify with:

```bash
curl https://api.clerk.com/v1/instance/redirect_urls \
  -H "Authorization: Bearer $CLERK_SECRET_KEY"
```

Expected: list contains `meli://clerk-callback`.

- [ ] **Step 8: Manual smoke test on iOS simulator**

Build and run on simulator (`npm run ios:run`). Verify:
1. App opens, Next.js sign-in page loads.
2. Tapping "Continue with Google" opens SFSafariViewController.
3. Completing Google → Clerk → redirect → app brought to front, signed in.

If the redirect doesn't reach the app, check Console.app for `meli://` URL events.

- [ ] **Step 9: Manual smoke test on Android emulator**

Same flow; uses Custom Tab. Verify cold-start case too: kill app fully, then complete OAuth in Custom Tab — app launches and signs in.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/app/sign-in/ frontend/src/app/sso-callback/ frontend/src/lib/clerk-mobile-oauth.ts mobile/shared/types.ts
git commit -m "feat(mobile-auth): Clerk social OAuth via Capacitor Browser + meli:// deep link"
```

---

## Task A8: App icons and splash

**Files:**
- Create: `mobile/resources/icon.png` (1024×1024 master)
- Create: `mobile/resources/splash.png` (2732×2732 master)
- Modify: iOS + Android asset folders (generated)

- [ ] **Step 1: Place a master icon**

Drop a 1024×1024 PNG (transparent background) at `mobile/resources/icon.png`. If no final icon exists yet, use a placeholder honey-yellow square with a white "M".

- [ ] **Step 2: Place a master splash**

Drop a 2732×2732 PNG at `mobile/resources/splash.png` (subject centered within a 1200×1200 safe area). Background should match `--color-background` from tokens.

- [ ] **Step 3: Install `@capacitor/assets` and generate**

```bash
cd mobile
npm install --save-dev @capacitor/assets
npx capacitor-assets generate --iconBackgroundColor '#FAF7EE' --splashBackgroundColor '#FAF7EE'
```

Expected: native asset folders populated:
- `mobile/ios/App/App/Assets.xcassets/AppIcon.appiconset/`
- `mobile/ios/App/App/Assets.xcassets/Splash.imageset/`
- `mobile/android/app/src/main/res/mipmap-*/`
- `mobile/android/app/src/main/res/drawable*/splash.png`

- [ ] **Step 4: Build both platforms and verify the icon shows**

```bash
npx cap sync
```

Open Xcode → Run on simulator. Inspect home screen — should show new icon. Same on Android emulator.

- [ ] **Step 5: Commit**

```bash
git add mobile/resources/ mobile/ios/App/App/Assets.xcassets/ mobile/android/app/src/main/res/ mobile/package.json mobile/package-lock.json
git commit -m "feat(mobile): app icon + splash assets generated from masters"
```

---

## Task A9: Apple privacy manifest

**Files:**
- Create: `mobile/ios/App/App/PrivacyInfo.xcprivacy`

- [ ] **Step 1: Write `PrivacyInfo.xcprivacy`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>NSPrivacyAccessedAPITypes</key>
    <array>
        <dict>
            <key>NSPrivacyAccessedAPIType</key>
            <string>NSPrivacyAccessedAPICategoryUserDefaults</string>
            <key>NSPrivacyAccessedAPITypeReasons</key>
            <array><string>CA92.1</string></array>
        </dict>
        <dict>
            <key>NSPrivacyAccessedAPIType</key>
            <string>NSPrivacyAccessedAPICategoryFileTimestamp</string>
            <key>NSPrivacyAccessedAPITypeReasons</key>
            <array><string>C617.1</string></array>
        </dict>
    </array>
    <key>NSPrivacyCollectedDataTypes</key>
    <array>
        <dict>
            <key>NSPrivacyCollectedDataType</key>
            <string>NSPrivacyCollectedDataTypeEmailAddress</string>
            <key>NSPrivacyCollectedDataTypeLinked</key><true/>
            <key>NSPrivacyCollectedDataTypeTracking</key><false/>
            <key>NSPrivacyCollectedDataTypePurposes</key>
            <array><string>NSPrivacyCollectedDataTypePurposeAppFunctionality</string></array>
        </dict>
        <dict>
            <key>NSPrivacyCollectedDataType</key>
            <string>NSPrivacyCollectedDataTypeAudioData</string>
            <key>NSPrivacyCollectedDataTypeLinked</key><true/>
            <key>NSPrivacyCollectedDataTypeTracking</key><false/>
            <key>NSPrivacyCollectedDataTypePurposes</key>
            <array><string>NSPrivacyCollectedDataTypePurposeAppFunctionality</string></array>
        </dict>
        <dict>
            <key>NSPrivacyCollectedDataType</key>
            <string>NSPrivacyCollectedDataTypeUserID</string>
            <key>NSPrivacyCollectedDataTypeLinked</key><true/>
            <key>NSPrivacyCollectedDataTypeTracking</key><false/>
            <key>NSPrivacyCollectedDataTypePurposes</key>
            <array><string>NSPrivacyCollectedDataTypePurposeAppFunctionality</string></array>
        </dict>
        <dict>
            <key>NSPrivacyCollectedDataType</key>
            <string>NSPrivacyCollectedDataTypeDeviceID</string>
            <key>NSPrivacyCollectedDataTypeLinked</key><true/>
            <key>NSPrivacyCollectedDataTypeTracking</key><false/>
            <key>NSPrivacyCollectedDataTypePurposes</key>
            <array><string>NSPrivacyCollectedDataTypePurposeAppFunctionality</string></array>
        </dict>
    </array>
    <key>NSPrivacyTracking</key><false/>
    <key>NSPrivacyTrackingDomains</key><array/>
</dict>
</plist>
```

- [ ] **Step 2: Add the manifest to the Xcode project**

Open `mobile/ios/App/App.xcworkspace`. Right-click `App` group → Add Files to "App"… → select `PrivacyInfo.xcprivacy` → ensure target is checked.

- [ ] **Step 3: Verify build still succeeds**

In Xcode: Product → Build (⌘B). Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add mobile/ios/App/App/PrivacyInfo.xcprivacy mobile/ios/App/App.xcodeproj/project.pbxproj
git commit -m "feat(mobile-ios): add Apple privacy manifest"
```

---

## Task A10: fastlane setup for iOS CI

**Files:**
- Create: `mobile/ios/fastlane/Appfile`
- Create: `mobile/ios/fastlane/Fastfile`
- Create: `mobile/ios/fastlane/Matchfile`
- Create: `mobile/ios/Gemfile`

- [ ] **Step 1: Add `Gemfile` with fastlane**

`mobile/ios/Gemfile`:

```ruby
source "https://rubygems.org"

gem "fastlane"
gem "cocoapods"
```

- [ ] **Step 2: `mobile/ios/fastlane/Appfile`**

```ruby
app_identifier("hk.ust.meli")
apple_id(ENV["APPLE_ID"])
team_id(ENV["APPLE_TEAM_ID"])
```

- [ ] **Step 3: `mobile/ios/fastlane/Matchfile`**

```ruby
git_url(ENV["MATCH_GIT_URL"])
storage_mode("git")
type("appstore")
app_identifier(["hk.ust.meli"])
username(ENV["APPLE_ID"])
```

- [ ] **Step 4: `mobile/ios/fastlane/Fastfile`**

```ruby
default_platform(:ios)

platform :ios do
  desc "Build and upload to TestFlight (internal track)"
  lane :build_and_upload do
    setup_ci if ENV["CI"]
    match(type: "appstore", readonly: true)

    cocoapods(podfile: "./Podfile")

    increment_build_number(
      build_number: ENV["GITHUB_RUN_NUMBER"] || Time.now.to_i.to_s,
      xcodeproj: "App.xcodeproj"
    )

    build_app(
      workspace: "App.xcworkspace",
      scheme: "App",
      export_method: "app-store",
      output_directory: "./build"
    )

    api_key = app_store_connect_api_key(
      key_id: ENV["APP_STORE_CONNECT_KEY_ID"],
      issuer_id: ENV["APP_STORE_CONNECT_ISSUER_ID"],
      key_filepath: ENV["APP_STORE_CONNECT_KEY_FILE"]
    )

    upload_to_testflight(
      api_key: api_key,
      skip_waiting_for_build_processing: true
    )
  end
end
```

- [ ] **Step 5: Bootstrap Match (one-time, run locally on the engineer's Mac)**

```bash
cd mobile/ios
bundle install
bundle exec fastlane match init
# Pick "git", paste the private match repo URL.
bundle exec fastlane match appstore
# This generates the App Store distribution cert + provisioning profile.
```

(The output is committed to the **separate match repo**, not this repo.)

- [ ] **Step 6: Verify a local build works**

```bash
bundle exec fastlane build_and_upload
```

This will fail at upload without ASC API key set — that's fine for local. Confirm the **build** step succeeds before committing.

- [ ] **Step 7: Commit**

```bash
git add mobile/ios/Gemfile mobile/ios/fastlane/
git commit -m "feat(mobile-ios): fastlane build_and_upload lane for TestFlight"
```

---

## Task A11: Android signing and gradle release config

**Files:**
- Modify: `mobile/android/app/build.gradle`
- Create: `mobile/android/keystore.properties.example`

- [ ] **Step 1: Generate the upload keystore (one-time, locally)**

```bash
cd mobile/android
keytool -genkey -v -keystore app/upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
# Follow prompts. Save passwords to 1Password.
```

This file is gitignored. Engineers re-clone don't get it.

- [ ] **Step 2: Create `keystore.properties.example`**

```properties
storeFile=app/upload-keystore.jks
storePassword=
keyAlias=upload
keyPassword=
```

- [ ] **Step 3: Wire signing into `app/build.gradle`**

Modify `mobile/android/app/build.gradle`. At the top of the file, before `android {`:

```groovy
def keystorePropertiesFile = rootProject.file("keystore.properties")
def keystoreProperties = new Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}
```

Inside `android { ... }`, add:

```groovy
signingConfigs {
    release {
        if (keystoreProperties['storeFile']) {
            storeFile file(keystoreProperties['storeFile'])
            storePassword keystoreProperties['storePassword']
            keyAlias keystoreProperties['keyAlias']
            keyPassword keystoreProperties['keyPassword']
        }
    }
}

buildTypes {
    release {
        signingConfig signingConfigs.release
        minifyEnabled false
        proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
    }
}
```

- [ ] **Step 4: Verify a release build works locally**

Create `mobile/android/keystore.properties` with real values (gitignored). Then:

```bash
cd mobile/android
./gradlew bundleRelease
```

Expected: `app/build/outputs/bundle/release/app-release.aab` produced.

- [ ] **Step 5: Verify the bundle is valid**

```bash
ls -la app/build/outputs/bundle/release/app-release.aab
# File should be > 1 MB
```

- [ ] **Step 6: Add `keystore.properties` to `.gitignore`** (already done in A1, verify)

```bash
grep keystore.properties .gitignore
```

Expected: file is listed.

- [ ] **Step 7: Commit**

```bash
git add mobile/android/app/build.gradle mobile/android/keystore.properties.example
git commit -m "feat(mobile-android): release signing config + upload keystore wiring"
```

---

## Task A12: GitHub Actions for tag-triggered builds

**Files:**
- Create: `.github/workflows/mobile-ios.yml`
- Create: `.github/workflows/mobile-android.yml`

- [ ] **Step 1: Write `.github/workflows/mobile-ios.yml`**

```yaml
name: Mobile iOS Release

on:
  push:
    tags:
      - 'mobile-v*'

jobs:
  build:
    runs-on: macos-14
    timeout-minutes: 60
    defaults:
      run:
        working-directory: mobile

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
          cache-dependency-path: mobile/package-lock.json

      - uses: maxim-lobanov/setup-xcode@v1
        with:
          xcode-version: '15.4'

      - uses: ruby/setup-ruby@v1
        with:
          ruby-version: '3.2'
          working-directory: mobile/ios

      - name: Install JS deps
        run: npm ci

      - name: Verify tokens fresh
        run: npm run tokens:verify

      - name: Cap sync iOS
        run: npx cap sync ios

      - name: Install pods
        working-directory: mobile/ios/App
        run: pod install

      - name: Write App Store Connect API key
        working-directory: mobile/ios
        env:
          APP_STORE_CONNECT_KEY_BASE64: ${{ secrets.APP_STORE_CONNECT_KEY_BASE64 }}
        run: |
          echo "$APP_STORE_CONNECT_KEY_BASE64" | base64 -d > AuthKey.p8
          echo "APP_STORE_CONNECT_KEY_FILE=$(pwd)/AuthKey.p8" >> $GITHUB_ENV

      - name: Fastlane build & upload
        working-directory: mobile/ios
        env:
          APPLE_ID: ${{ secrets.APPLE_ID }}
          APPLE_TEAM_ID: ${{ secrets.APPLE_TEAM_ID }}
          MATCH_GIT_URL: ${{ secrets.MATCH_GIT_URL }}
          MATCH_PASSWORD: ${{ secrets.MATCH_PASSWORD }}
          APP_STORE_CONNECT_KEY_ID: ${{ secrets.APP_STORE_CONNECT_KEY_ID }}
          APP_STORE_CONNECT_ISSUER_ID: ${{ secrets.APP_STORE_CONNECT_ISSUER_ID }}
          GITHUB_RUN_NUMBER: ${{ github.run_number }}
        run: |
          bundle install
          bundle exec fastlane build_and_upload
```

- [ ] **Step 2: Write `.github/workflows/mobile-android.yml`**

```yaml
name: Mobile Android Release

on:
  push:
    tags:
      - 'mobile-v*'

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    defaults:
      run:
        working-directory: mobile

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'
          cache-dependency-path: mobile/package-lock.json

      - uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '17'

      - name: Install JS deps
        run: npm ci

      - name: Verify tokens fresh
        run: npm run tokens:verify

      - name: Cap sync Android
        run: npx cap sync android

      - name: Decode keystore
        run: |
          mkdir -p android/app
          echo "${{ secrets.ANDROID_KEYSTORE_BASE64 }}" | base64 -d > android/app/upload-keystore.jks

      - name: Write keystore.properties
        run: |
          cat > android/keystore.properties <<EOF
          storeFile=app/upload-keystore.jks
          storePassword=${{ secrets.ANDROID_KEYSTORE_PASSWORD }}
          keyAlias=upload
          keyPassword=${{ secrets.ANDROID_KEY_PASSWORD }}
          EOF

      - name: Build release bundle
        working-directory: mobile/android
        run: ./gradlew bundleRelease --no-daemon

      - name: Upload to Play Console (internal track)
        uses: r0adkll/upload-google-play@v1
        with:
          serviceAccountJsonPlainText: ${{ secrets.PLAY_CONSOLE_SERVICE_ACCOUNT_JSON }}
          packageName: hk.ust.meli
          releaseFiles: mobile/android/app/build/outputs/bundle/release/app-release.aab
          track: internal
          status: completed
```

- [ ] **Step 3: Required GitHub Secrets to set** (do this in repo Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `APPLE_ID` | Apple ID email used for App Store Connect |
| `APPLE_TEAM_ID` | 10-char team ID |
| `MATCH_GIT_URL` | Private match repo URL (with credentials) |
| `MATCH_PASSWORD` | Match cert encryption password |
| `APP_STORE_CONNECT_KEY_ID` | ASC API key ID |
| `APP_STORE_CONNECT_ISSUER_ID` | ASC API issuer ID |
| `APP_STORE_CONNECT_KEY_BASE64` | `base64 -i AuthKey.p8` of the .p8 file |
| `ANDROID_KEYSTORE_BASE64` | `base64 -i app/upload-keystore.jks` |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_PASSWORD` | Key password (often same as keystore) |
| `PLAY_CONSOLE_SERVICE_ACCOUNT_JSON` | Service account JSON for Play Console upload (full file contents) |

- [ ] **Step 4: Trigger a dry build by tagging an early commit**

```bash
git tag mobile-v0.1.0-rc1
git push origin mobile-v0.1.0-rc1
```

Watch GitHub Actions. Expected: both workflows run; iOS workflow likely fails at the upload step the first time (App Store Connect needs a valid app record set up — see Task A13). Android may succeed if Play Console app already exists.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/mobile-ios.yml .github/workflows/mobile-android.yml
git commit -m "ci(mobile): tag-triggered TestFlight + Play Internal builds"
```

---

## Task A13: App Store Connect + Play Console app records

This task is **manual configuration**, not code. Document it as a runbook.

**Files:**
- Create: `mobile/docs/store-setup.md`

- [ ] **Step 1: Apple Developer enrollment**

If using individual: enroll at https://developer.apple.com/programs/enroll/. ($99/year. 1-2 day approval.)
If using HKUST org: requires D-U-N-S verification. Start the process now in parallel; use individual for the pilot.

- [ ] **Step 2: Create App Store Connect app record**

1. App Store Connect → My Apps → "+" → New App
2. Platform: iOS
3. Name: Meli
4. Bundle ID: `hk.ust.meli` (must match `appId` in `capacitor.config.ts`)
5. SKU: `meli-mobile-ios`
6. User access: Full Access

- [ ] **Step 3: Create App Store Connect API key**

App Store Connect → Users and Access → Integrations → App Store Connect API → "+"
- Name: meli-ci
- Access: Developer
- Download the `.p8` file (one-time download — save securely)
- Note the Key ID and Issuer ID — feed both as GitHub Secrets per A12 Step 3

- [ ] **Step 4: Create Play Console app record**

1. Google Play Console → Create app
2. App name: Meli
3. Default language: English (United States)
4. App or game: App
5. Free or paid: Free
6. Click Create

- [ ] **Step 5: Create Play Console service account for CI uploads**

1. Google Play Console → Setup → API access → Create new service account
2. In Google Cloud Console: download JSON key for the service account
3. Back in Play Console: grant "Release manager" role to the service account
4. Paste the full JSON contents into GitHub Secret `PLAY_CONSOLE_SERVICE_ACCOUNT_JSON`

- [ ] **Step 6: Upload an initial AAB by hand**

The CI job uses `r0adkll/upload-google-play` which requires the app to have at least one prior upload (Play Console limitation). One-time:

```bash
cd mobile/android
./gradlew bundleRelease
# Upload app-release.aab manually via Play Console → Internal testing → Create release
```

After this, CI uploads work normally.

- [ ] **Step 7: Write `mobile/docs/store-setup.md`** capturing the above as a runbook for the next engineer

(See content above — copy into the file with no edits.)

- [ ] **Step 8: Commit**

```bash
git add mobile/docs/store-setup.md
git commit -m "docs(mobile): App Store Connect + Play Console setup runbook"
```

---

## Task A14: First successful TestFlight build

- [ ] **Step 1: Tag and push to trigger CI**

```bash
git tag mobile-v0.1.0
git push origin mobile-v0.1.0
```

- [ ] **Step 2: Watch GitHub Actions until both jobs succeed**

Expected:
- iOS job uploads to TestFlight; processing takes ~10-30 min on Apple's side
- Android job uploads to Play Internal Testing; processing takes minutes

- [ ] **Step 3: Verify TestFlight build appears**

App Store Connect → TestFlight → Builds tab → `0.1.0 (build N)` should be listed. Status starts as "Processing" → "Ready to Submit" or "Internal Testing" available.

- [ ] **Step 4: Verify Play Console build appears**

Play Console → Internal testing → Releases → confirm `0.1.0` listed and ready.

- [ ] **Step 5: Add internal testers**

- TestFlight: App Store Connect → TestFlight → Internal Testing → Add team members
- Play Console: Internal testing → Testers tab → Add tester emails

- [ ] **Step 6: Install on a real device and verify it loads the WebView**

Open TestFlight app on iPhone → install Meli → tap to launch.

Expected:
- Splash screen shows for ~1.2s (color matches `--color-background`)
- WebView loads the production Next.js app
- If signed out, sign-in page appears
- "Continue with Google" opens Safari (in-app), completes, returns to app signed in

Same on Android via Internal Testing track.

- [ ] **Step 7: Commit any docs/runbook touch-ups discovered during the smoke test**

```bash
git add mobile/docs/
git commit -m "docs(mobile): smoke-test refinements after first TestFlight"
```

---

## Task A15: WebView keyboard QA pass

The spec calls out keyboard handling as a known iOS issue. This task is a focused half-day to verify it works.

**Files:** none (verification + fixes)

- [ ] **Step 1: Install Capacitor Keyboard plugin**

```bash
cd mobile
npm install @capacitor/keyboard
npx cap sync
```

- [ ] **Step 2: Configure keyboard behavior in `capacitor.config.ts`**

Update the `plugins` block:

```ts
plugins: {
  SplashScreen: {
    launchShowDuration: 1200,
    backgroundColor: '#FAF7EE',
    androidScaleType: 'CENTER_CROP'
  },
  Keyboard: {
    resize: 'native',           // iOS: WebView resizes when keyboard shows
    resizeOnFullScreen: true,
    style: 'default'
  }
}
```

- [ ] **Step 3: Verify `viewport-fit=cover` is set in Next.js**

```bash
grep -r "viewport-fit" frontend/src/
```

Expected: at least one match in `app/layout.tsx` or a metadata config. If absent, add to `frontend/src/app/layout.tsx`:

```tsx
export const viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover'
};
```

- [ ] **Step 4: Verify safe-area CSS is in global styles**

```bash
grep -E "safe-area-inset|env\(" frontend/src/app/globals.css
```

Expected: at least one match. If absent, add to `globals.css`:

```css
:root {
  --safe-top: env(safe-area-inset-top, 0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
}

body {
  padding-top: var(--safe-top);
  padding-bottom: var(--safe-bottom);
}
```

- [ ] **Step 5: Test keyboard on iOS**

Run in Xcode simulator. Open sign-in page. Tap email field. Verify:
- Keyboard slides up
- Email field stays visible (not covered)
- Closing keyboard returns layout to normal
- No "rubber band" overshoot

- [ ] **Step 6: Test keyboard on Android**

Same flow. Verify:
- Keyboard appears
- WebView content shifts to keep field visible
- No layout jump

- [ ] **Step 7: Commit**

```bash
git add mobile/capacitor.config.ts mobile/package.json mobile/package-lock.json frontend/src/app/layout.tsx frontend/src/app/globals.css
git commit -m "feat(mobile): keyboard plugin + safe-area handling"
```

---

## Task A16: CORS update and final verification

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Read current CORS config**

```bash
grep -n "allow_origins" backend/app/main.py
```

Note the line number.

- [ ] **Step 2: Extend allow-list to include native origins**

In `backend/app/main.py`, locate the `app.add_middleware(CORSMiddleware, ...)` block and update `allow_origins`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "capacitor://localhost",   # iOS WebView origin
        "http://localhost",         # Android WebView origin (capacitor uses http for android by default)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 3: Add a test confirming the new origins are allowed**

Add to `backend/tests/test_cors.py` (create if it doesn't exist):

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_cors_allows_capacitor_ios_origin():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.options(
            "/api/courses",
            headers={
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.headers.get("access-control-allow-origin") == "capacitor://localhost"


@pytest.mark.asyncio
async def test_cors_allows_capacitor_android_origin():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.options(
            "/api/courses",
            headers={
                "Origin": "http://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert r.headers.get("access-control-allow-origin") == "http://localhost"
```

- [ ] **Step 4: Run the test to verify**

```bash
cd backend
source .venv/bin/activate
pytest tests/test_cors.py -v
```

Expected: 2/2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_cors.py
git commit -m "feat(backend): allow Capacitor WebView origins in CORS"
```

---

## Task A17: README update for the workspace root

**Files:**
- Modify: `README.md` (root)

- [ ] **Step 1: Add a "Mobile" section to root README**

Append:

```markdown

## Mobile

The iOS + Android app lives in `mobile/`. It's a Capacitor wrapper around
the production Next.js web app, with two native screens (pronunciation
and flashcard review) added in Plans D and E.

```bash
cd mobile
npm install
npm run cap:sync
npm run ios:open       # opens Xcode
npm run android:open   # opens Android Studio
```

Releases are tag-triggered (`mobile-vX.Y.Z`) and ship to TestFlight +
Play Internal Testing.

See `mobile/README.md` and `mobile/docs/store-setup.md` for details.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add mobile workspace section to root README"
```

---

## Acceptance criteria for Plan A

- [ ] `npm install && npm run cap:sync` from `mobile/` works on a fresh clone
- [ ] Xcode build of `mobile/ios/App/App.xcworkspace` succeeds with no warnings
- [ ] Android Studio build of `mobile/android/` succeeds with no warnings
- [ ] App launches, splash → WebView, loads production Next.js
- [ ] Email/password Clerk sign-in works in WebView
- [ ] "Continue with Google" works on both platforms via deep-link callback
- [ ] App is installed on a real iPhone via TestFlight
- [ ] App is installed on a real Android via Play Internal Testing track
- [ ] Both stores show app icon, splash, "Meli" name, version 0.1.0
- [ ] CORS allows `capacitor://localhost` and `http://localhost`
- [ ] `npm run tokens:verify` is part of CI on both mobile workflows
- [ ] `frontend/src/lib/capacitor.ts` exports `isNative()` + `getPlatform()`, all unit tests pass
