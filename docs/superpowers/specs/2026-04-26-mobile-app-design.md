# Meli Mobile App — Design Spec

**Date:** 2026-04-26
**Status:** Draft (pending user review)
**Owner:** baduru
**Scope:** iOS + Android mobile app for Meli, derived from the existing Next.js 16 web app.

---

## 1. Goals & non-goals

### Goals (the "why")

- **App Store presence.** Students find "Meli" in the App Store / Play Store and install it like any other app.
- **Native feature access.** Reliable microphone capture for pronunciation practice, haptics + smooth gestures for flashcard review, push notifications for live-quiz invites and reminders, camera for document scans.
- **Better mobile UX.** Native-feeling interactions where they matter most (pronunciation, flashcards, push); the rest reuses the proven web UI.

### Explicit non-goals (for v1)

- **No separate codebase.** The web app remains the source of truth for non-native screens; the mobile app reuses it via a WebView.
- **No offline support.** Online-only for v1. The phone shows a "no internet" state if disconnected.
- **No tablet-optimised layouts.** Phone-first; iPads/tablets use the same layout scaled.
- **No notification center beyond the agreed five types.** No "streak broken", no leaderboard pings, etc.
- **No Apple Watch / Wear OS companion.**

---

## 2. Locked decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Architecture | **Capacitor wrapping the existing Next.js app** + selective native screens |
| 2 | Native screens | **Pronunciation practice** + **Flashcard review** (Swift on iOS, Kotlin on Android) |
| 3 | Distribution | **TestFlight + Play Internal Testing pilot first**, then public listing |
| 4 | Offline | **Online-only** |
| 5 | Notifications | **Full notification center** (live-quiz invites, study reminders, instructor announcements, course updates, content-ready) with in-app feed, deep links, instructor compose UI |
| 6 | Resources | Small team (1-2 engineers + product owner), Mac available |
| 7 | Auth | **Clerk hosted pages inside WebView** + OAuth via Capacitor Browser plugin + custom URL scheme `meli://` for callback |

### Why Capacitor and not Flutter / React Native

| | Effort | Code reuse | Native feel |
|---|---|---|---|
| Capacitor + Swift/Kotlin screens (chosen) | 8-12 weeks | ~95% of Next.js reused | Native where it matters; WebView elsewhere |
| Flutter rewrite | 4-6 months | ~0% | Fully native |
| React Native rewrite | 3-5 months | ~30% (logic/types only) | Fully native |

Flutter / React Native are *alternative chassis*, not modules pluggable into Capacitor. Embedding Flutter add-to-app or RN brownfield in Capacitor is technically possible but means three rendering stacks in one binary. We deliberately avoid that.

---

## 3. Architecture

```
                   ┌──────────────────────────────────────┐
                   │        Mobile App (one binary)       │
                   │                                      │
                   │  ┌─────────────────────────────────┐ │
                   │  │  Capacitor shell (iOS / Android)│ │
                   │  │  • WebView host                 │ │
                   │  │  • Native bridge (JS ↔ native)  │ │
                   │  │  • Plugins: push, camera,       │ │
                   │  │    haptics, browser, network,   │ │
                   │  │    statusbar, splashscreen,     │ │
                   │  │    local-notifications          │ │
                   │  └────────────┬────────────────────┘ │
                   │               │                      │
                   │   ┌───────────┴────────────┐         │
                   │   │ WebView: Next.js app   │         │
                   │   │ (loaded from prod URL) │         │
                   │   │  dashboard, courses,   │         │
                   │   │  quizzes, summaries,   │         │
                   │   │  documents, live quiz, │         │
                   │   │  sign-in, settings,    │         │
                   │   │  notifications feed,   │         │
                   │   │  instructor compose    │         │
                   │   └────────────────────────┘         │
                   │                                      │
                   │   ┌────────────────────────┐         │
                   │   │ Native module:         │         │
                   │   │  Pronunciation         │         │
                   │   │  Swift + Kotlin        │         │
                   │   └────────────────────────┘         │
                   │                                      │
                   │   ┌────────────────────────┐         │
                   │   │ Native module:         │         │
                   │   │  Flashcard review      │         │
                   │   │  Swift + Kotlin        │         │
                   │   └────────────────────────┘         │
                   └──────────────┬───────────────────────┘
                                  │ HTTPS + Bearer JWT
                                  ▼
                   ┌──────────────────────────────────────┐
                   │     FastAPI backend (existing)       │
                   │  + new: notification_devices,        │
                   │         notifications,               │
                   │         announcements,               │
                   │         notifier service             │
                   └──────────────────────────────────────┘
                                  ▲
                                  │ APNs / FCM
                   ┌──────────────┴───────────────────────┐
                   │  Push delivery (Apple / Google)      │
                   └──────────────────────────────────────┘
```

### Key architectural rules

- **WebView is the default.** Native is the exception, not the rule.
- **WebView loads production Next.js over HTTPS** (`server.url` in `capacitor.config.ts`). Each web deploy is automatically a "mobile content release" — no app rebuild needed for non-native UI changes.
- **Native screens are full-screen modal** over the WebView. They open via `App.openNative({screen, params})`, run their own UI, and return a result object on close.
- **Native screens have no auth state and no data store.** They receive a JWT from the WebView at open time and call existing FastAPI endpoints. Token refresh stays in the WebView.
- **One backend.** No mobile-specific API. New endpoints (Section 6) serve both web and mobile uniformly.

---

## 4. Code boundary — what's web vs. native

| Concern | Where it runs | Code |
|---|---|---|
| All routes (`/dashboard/*`, `/sign-in`, `/courses/*`, `/quiz/*`, `/summary/*`, `/live/*`, `/documents/*`) | WebView | Existing Next.js — zero changes |
| Auth (Clerk JWT, session) | WebView | Existing — Clerk hosted pages + OAuth callback (Section 5) |
| API calls (`apiFetch`, TanStack Query) | WebView | Existing — backend doesn't know it's a WebView |
| Camera / document scan | WebView calls Capacitor plugin | `@capacitor/camera`, ~30 lines into existing upload UI |
| Haptics on quiz answer, navigation feedback | WebView calls Capacitor plugin | `@capacitor/haptics` |
| Status bar / safe area / splash | Capacitor config | YAML/plist/manifest only |
| **Pronunciation screen** | **Native (Swift + Kotlin)** | NEW |
| **Flashcard review screen** | **Native (Swift + Kotlin)** | NEW |
| Push receive (foreground + background tap) | Native + Capacitor plugin | `@capacitor/push-notifications` + small wrapper |
| Notification feed UI | WebView | New Next.js route `/dashboard/notifications` |
| Local reminders settings | WebView | New Next.js route `/dashboard/settings/reminders` |
| Instructor announcement compose | WebView | New Next.js route `/dashboard/courses/:cid/announcements/new` |

### Boundary discipline

- WebView calls into native via a typed plugin interface (`mobile/shared/types.ts`).
- Native calls into WebView only via "screen close → returns result". No native-pushed events back to the WebView except through the Capacitor lifecycle (e.g., `appStateChange`).
- After a native screen closes, the WebView **always** invalidates the relevant TanStack Query keys (e.g., `['flashcards', courseId]`, `['streak']`, `['pronunciation', sessionId]`) to refetch fresh state.

---

## 5. Authentication (Clerk on mobile)

### Sign-in flow

WebView loads `https://meli.app/`. Clerk middleware redirects unauthenticated users to `/sign-in`. The hosted Clerk UI runs inside the WebView exactly as in a desktop browser — email/password works without any extra plumbing.

### OAuth (Continue with Google)

Google blocks OAuth inside WebViews (disallowed-user-agents policy). To support social sign-in:

1. Tapping "Continue with Google" calls `Browser.open({ url })` (Capacitor Browser plugin) which opens an SFSafariViewController on iOS / Custom Tab on Android over the WebView.
2. Google authenticates the user; Clerk completes the flow; Clerk redirects to `meli://clerk-callback?token=...`.
3. The custom URL scheme is registered in `Info.plist` (iOS) and `AndroidManifest.xml` (Android). Capacitor's `App.addListener('appUrlOpen', ...)` catches the callback and forwards the token to the WebView's Clerk client.
4. WebView's Clerk client consumes the token, signs in, and the app's normal route guard takes over.

Clerk dashboard configuration: add `meli://clerk-callback` to the allowed redirect URLs.

### Session persistence

Capacitor's WebView keeps cookies and localStorage between launches. Clerk's session survives close/reopen exactly like a real browser. No native keychain, no "remember me" wiring.

### JWT into native screens

Every `getToken()` call passes `{ template: 'backend' }` so the JWT carries the email claim the FastAPI deps need. When a native screen opens:

```ts
const token = await clerk.session.getToken({ template: 'backend' });
await App.openNative({ screen: 'pronunciation', params: { token, ... }});
```

Native screen holds the token in memory only. On 401:

1. Native screen closes immediately, returning `{ error: 'unauthorized' }`.
2. WebView calls `clerk.session.touch()` to force refresh and reopens the screen.

### Push token ↔ user mapping

On APNs/FCM token receipt, the app POSTs to `/api/notifications/devices` with the user's JWT. Backend stores `(user_id, platform, push_token, last_seen_at)`. Sign-out triggers `DELETE /api/notifications/devices/:token`.

### Backend changes for auth

- **None to existing auth.** `get_current_user` keeps verifying Clerk JWTs unchanged.
- **CORS allow-list adds** `capacitor://localhost` and `http://localhost` for native-screen direct API calls. ~3 lines in `app/main.py`.

---

## 6. Native screens

### 6.1 Pronunciation screen

**Why native:** mic permission UX is reliable, audio capture is high-fidelity, the live waveform stays at 60fps without WebAudio quirks. Mobile WebViews routinely cut audio on backgrounding or route change; native survives that.

**iOS (Swift)**

- `AVAudioSession` configured `.record` category, `.measurement` mode (low-pass filter off, suitable for speech).
- `AVAudioEngine` with a `tap` on the input node → buffer pushed to a `CircularBuffer`.
- `AVAudioRecorder` writes the segment to a temp `.wav` for upload.
- `MTKView` (Metal-backed) for waveform — 60fps.
- Foreground-only recording (no background mode) — keeps App Store review trivial.

**Android (Kotlin)**

- `AudioRecord` with `MediaRecorder.AudioSource.VOICE_RECOGNITION` (built-in noise suppression + AGC).
- 16 kHz mono 16-bit PCM → encoded to WAV in `MediaCodec`.
- Custom `View` with `Canvas.drawPath` for waveform; `Choreographer` for v-sync ticks.

**API contracts (existing endpoints in `app/api/speech.py`)**

```
POST /api/speech/generate-prompts                       (JSON: course_id, difficulty)
  → 200 { prompts: PracticePrompt[] }                   # used to populate reference text

POST /api/speech/grade                                  (multipart: audio, reference_text, course_id, language)
  → 200 { score, words: WordScore[], xp_awarded }

GET  /api/speech/courses/{course_id}/pronunciation-history
  → 200 { entries: PronunciationHistoryEntry[] }
```

The existing speech API is **stateless per recording**: no server-side session concept, no per-utterance session ID. The native screen aggregates a "session" purely client-side (sequence of recordings, each graded independently, totals computed on-device).

**Plugin interface**

- Inputs: `{ token, courseId, language, prompts? }` (prompts optional — if omitted, screen calls `generate-prompts` itself)
- Returns: `{ wordsAttempted, averageScore, totalXp }`
- WebView refreshes `['pronunciation-history', courseId]`, `['streak']`, dashboard XP widget on close.

**Estimate:** ~600-900 LOC Swift, ~700-1000 LOC Kotlin. ~2-3 weeks per platform.

### 6.2 Flashcard review screen

**Why native:** swipe-to-rate gesture, card-stack depth, haptic feedback on rating. WebView libraries can mimic this but rubber-banding, fling physics, and 60fps card transforms degrade noticeably on mid-range Android. Haptics also drastically better natively.

**iOS (Swift)**

- SwiftUI `ZStack` with 3 preloaded cards (current + next + next-next).
- Drag gesture → live transform (rotation + translation + scale of cards behind).
- On release: spring animation commits (off-screen) or rubber-bands back.
- `CoreHaptics`: light tap on Easy, medium on Good, heavy on Hard.
- Bottom-sheet rating buttons as accessibility fallback.

**Android (Kotlin)**

- Jetpack Compose `Box` with `Modifier.draggable` + `animateFloatAsState`.
- Same 3-card depth pattern.
- `VibratorManager.vibrate(VibrationEffect.predefined(EFFECT_TICK))` for haptics.
- Predictive back gesture handling (Android 14+) so back-swipe doesn't accidentally rate.

**API contracts (existing endpoints in `app/api/revision.py`)**

```
POST /api/courses/{course_id}/revision/start          (JSON: difficulty?, mode?)
  → 200 { session_id, first_item, total_items }

GET  /api/revision/sessions/{session_id}/next
  → 200 { item, remaining }                            # null when session done

POST /api/revision/sessions/{session_id}/answer       (JSON: item_id, rating, response_time_ms)
  → 200 { correct, srs_update, next_due_at }

POST /api/revision/sessions/{session_id}/end
  → 200 { stats, streak, xp_awarded }

GET  /api/revision/sessions/{session_id}
  → 200 { session metadata }
```

The existing revision API is the right backend for native flashcard review: it's a server-side session with explicit start, next, answer, end. The native screen drives this exactly like the existing web flashcard reviewer does — no new endpoints needed.

For flashcard-set "study mode" (a different surface — reviewing a specific set rather than mixed daily revision), there's also `PUT /api/flashcard-sets/{set_id}/progress`. The native screen targets the revision-session API as the primary use case; set-study mode stays in the WebView for v1.

**Optimization:** prefetch the `next` item while the user is on the current card. On slow connections, show a small loader if the buffer empties.

**Plugin interface**

- Inputs: `{ token, courseId, difficulty?, mode? }`
- Returns: `{ cardsReviewed, sessionStats, xpAwarded }`
- WebView refreshes `['revision', courseId]`, `['streak']`, dashboard XP/due widgets on close.

**Estimate:** ~500-800 LOC Swift, ~600-900 LOC Kotlin. ~2-3 weeks per platform with proper gesture/haptic polish.

### 6.3 Shared design tokens

```
frontend/src/styles/tokens.css   ←  source of truth
   │
   ├─→ extracted to shared/tokens.json (build script)
   │     │
   │     ├─→ Swift: tokens.swift (UIColor extensions)
   │     └─→ Kotlin: Tokens.kt    (Color object)
```

Build script (`mobile/scripts/extract-tokens.mjs` + `codegen.mjs`) runs in CI; build fails if native files are stale relative to `tokens.css`. Palette change in `tokens.css` propagates to native at next build.

### 6.4 Native UI conventions

- Platform-native primitives: SF Symbols on iOS, Material 3 on Android.
- Color/typography tokens inherited from web via codegen.
- No tab bar in native screens; they're modal — when closed, user returns to the WebView page that opened them.
- Animate in/out matching platform conventions (sheet from below on iOS, fade+scale on Android).

---

## 7. Notification system (full center)

### 7.1 Notification types

| Type | Trigger | Delivery | Deep link target |
|---|---|---|---|
| **Live-quiz invite** | Instructor starts a live session | Server push (APNs/FCM) | `/dashboard/courses/:cid/live/:sid` |
| **Study reminder** | Student-set local schedule | Local notification (on-device) | `/dashboard/flashcards?courseId=:cid` |
| **Instructor announcement** | Instructor composes from dashboard | Server push to enrolled students | `/dashboard/courses/:cid/announcements/:aid` |
| **Course update** | New document/quiz/summary added | Server push (batched, throttled) | `/dashboard/courses/:cid/...` |
| **Content-ready** | Async generation completes | Server push to requesting user | `/dashboard/courses/:cid/quizzes/:qid` (etc.) |

### 7.2 Throttling & batching rules

- **Course updates** batched within a 30-minute window (one notification: "5 new documents in CS101"); max 1/day per (course, user).
- **Live-quiz invites** real-time, no batching, one per session start.
- **Announcements** with `send_mode='digest'` flushed daily at 8am via existing scheduler infrastructure (analogous to `canvas_sync.py`). `send_mode='now'` delivers immediately.
- **Content-ready** real-time, but suppressed if the user is currently in the WebView on the same course (heuristic: foreground state + last-seen route).
- **Study reminders** user-controlled, capped at 5 active schedules per user.

### 7.3 Backend additions

**New tables (single Alembic migration)**

```sql
notification_devices (
  id           uuid pk,
  user_id      uuid fk,
  platform     text,                -- 'ios' | 'android'
  push_token   text  unique,
  app_version  text,
  last_seen_at timestamptz,
  created_at   timestamptz
)

notifications (
  id           uuid pk,
  user_id      uuid fk,             -- recipient
  type         text,                -- 'live_quiz_invite' | 'announcement' | 'course_update' | 'content_ready'
  title        text,
  body         text,
  deep_link    text,
  data         jsonb,
  read_at      timestamptz null,
  delivered_at timestamptz null,
  created_at   timestamptz
)

announcements (
  id           uuid pk,
  course_id    uuid fk,
  author_id    uuid fk,
  title        text,
  body         text,
  send_mode    text,                -- 'now' | 'digest'
  scheduled_at timestamptz null,
  sent_at      timestamptz null,
  retracted_at timestamptz null,
  created_at   timestamptz
)
```

**New endpoints**

```
POST   /api/notifications/devices                # register/refresh push token
DELETE /api/notifications/devices/:token         # on sign-out
GET    /api/notifications?cursor=...&limit=20    # paginated feed
POST   /api/notifications/:id/read               # mark single read
POST   /api/notifications/read-all
GET    /api/notifications/unread-count           # for badge

POST   /api/courses/:cid/announcements           # instructor compose
GET    /api/courses/:cid/announcements           # instructor list
DELETE /api/courses/:cid/announcements/:aid      # instructor retract
```

**New service `app/services/notifier.py`**

```python
def dispatch(user_id, type, title, body, deep_link, data):
    notif = insert_notification(...)
    devices = list_devices(user_id)
    for d in devices:
        try:
            send_apns_or_fcm(d, title, body, deep_link, data)
        except (TokenInvalidated, TokenExpired):
            delete_device(d.id)
    update_delivered_at(notif.id)
```

**Call-sites** that already trigger work simply call `notifier.dispatch(...)`:

- `live.py` when a session starts → live-quiz invite to enrolled students.
- `worker.py` when async generation completes → content-ready to the requesting user.
- New periodic task in `worker.py` (every 30 min) for batched course-update notifications.
- Daily 8am cron for announcement digest flush.

### 7.4 Mobile push wiring

```ts
import { PushNotifications } from '@capacitor/push-notifications';

await PushNotifications.requestPermissions();
await PushNotifications.register();

PushNotifications.addListener('registration', async ({ value: token }) => {
  await apiFetch('/api/notifications/devices', {
    method: 'POST',
    body: JSON.stringify({ token, platform })
  });
});

PushNotifications.addListener('pushNotificationActionPerformed', ({ notification }) => {
  handleDeepLink(notification.data.deep_link);
});

PushNotifications.addListener('pushNotificationReceived', (n) => {
  invalidateNotificationFeed();
});
```

**iOS specifics:** APNs production key (`.p8`) in App Store Connect; `aps-environment` entitlement; "Push Notifications" capability in Xcode.

**Android specifics:** `google-services.json` from Firebase console; FCM service account JSON in backend secrets; Android 13+ runtime POST_NOTIFICATIONS permission (handled by Capacitor plugin).

### 7.5 Local notifications (study reminders)

`@capacitor/local-notifications`. **No backend involvement.**

```ts
await LocalNotifications.schedule({
  notifications: [{
    id: 1001,
    title: 'Time to review',
    body: '12 cards due in CS101',
    schedule: { on: { weekday: 1, hour: 9, minute: 0 }, repeats: true },
    extra: { deep_link: '/dashboard/flashcards?courseId=...' }
  }]
});
```

Tap handler shares the same deep-link routing as push.

### 7.6 In-app notification feed

New Next.js route `/dashboard/notifications`:

- TanStack Query infinite scroll over `GET /api/notifications`.
- Each item: icon (per type), title, body, relative time, unread dot.
- Tap → mark read + navigate to `deep_link`.
- Top-right "mark all read".
- Navbar bell with unread count badge (polled every 60s when foreground; refreshed via `pushNotificationReceived` listener).

### 7.7 Instructor compose UI

New Next.js route `/dashboard/courses/:cid/announcements/new` (gated by `require_instructor`):

- Title input.
- Markdown body — textarea + live `ReactMarkdown` preview (the existing `summary-card` already uses `react-markdown` for rendering; the compose form pairs a plain textarea with the same renderer, ~half a day of work).
- Send mode toggle: "Send now" / "Add to morning digest".
- Preview pane.
- Submit → `POST /api/courses/:cid/announcements` → `notifier.dispatch` (or queues for digest).

### 7.8 Deep link routing (single source of truth)

```ts
function handleDeepLink(path: string) {
  if (capacitorIsNative()) {
    router.push(path);
  } else {
    window.location.href = path;
  }
}
```

**Cold start:** if app was killed and user taps a notification, Capacitor delivers the launch notification via `getDeliveredNotifications()` after `App.addListener('appStateChange', ...)` fires. Held until Clerk session restores, then navigated.

### 7.9 Future cut-down order (if scope tightens)

If timeline pressure forces scope cuts later, drop in this order:

1. Course update batched notifications.
2. Announcement digest mode (just send-now).
3. Instructor announcements entirely.
4. Content-ready (poll feed instead).
5. **Floor:** live-quiz invites + study reminders. Never cut these.

---

## 8. Build, distribution, infrastructure

### 8.1 Repo layout

```
cle/
├── backend/                  (existing)
├── frontend/                 (existing — adds notification feed/settings/announcements routes)
└── mobile/                   ◄── NEW
    ├── capacitor.config.ts
    ├── ios/
    │   ├── App/
    │   ├── App/Plugins/
    │   │   ├── PronunciationPlugin.swift
    │   │   └── FlashcardsPlugin.swift
    │   └── Podfile
    ├── android/
    │   ├── app/
    │   ├── app/src/main/java/.../plugins/
    │   │   ├── PronunciationPlugin.kt
    │   │   └── FlashcardsPlugin.kt
    │   └── build.gradle
    ├── shared/
    │   ├── tokens.json
    │   └── types.ts
    └── scripts/
        ├── extract-tokens.mjs
        └── codegen.mjs
```

`mobile/` is a sibling of `frontend/` and `backend/`. No nested workspaces, no submodules.

### 8.2 capacitor.config.ts

```ts
import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'hk.ust.meli',
  appName: 'Meli',
  webDir: 'public',
  server: {
    url: 'https://meli.app',
    cleartext: false,
    androidScheme: 'https',
    iosScheme: 'https',
    allowNavigation: ['*.clerk.accounts.dev', 'accounts.google.com']
  },
  plugins: {
    PushNotifications: { presentationOptions: ['badge', 'sound', 'alert'] },
    LocalNotifications: { smallIcon: 'ic_stat_meli', iconColor: '#FFB000' },
    SplashScreen: { launchShowDuration: 1200, backgroundColor: '#FAF7EE' }
  },
  ios: { contentInset: 'always' },
  android: { allowMixedContent: false }
};
export default config;
```

### 8.3 Build & deploy pipeline

**Web release (existing)**: `git push main` → Vercel deploys → users see new web → mobile WebView sees new on next launch (auto). No app rebuild needed.

**Native release (new)**: only on tag pushes (`mobile-v0.1.0`) or path filter (`mobile/**`, `frontend/src/styles/tokens.css`). GitHub Actions:

- iOS job (macOS runner): `npx cap sync ios && cd ios && fastlane build_and_upload` → TestFlight internal track.
- Android job (ubuntu runner): `npx cap sync android && cd android && ./gradlew bundleRelease` → Play Console internal testing track.

Web-only changes don't burn macOS-runner minutes.

### 8.4 Signing & certificates

- **iOS**: Apple Developer account ($99/yr) → App Store Connect app → "Meli". Automatic signing for dev, fastlane Match-stored cert for CI. 1-2 days first-time setup.
- **Android**: Google Play Developer account ($25 once) → Play Console app → upload key in GitHub Secrets. Half a day.

### 8.5 Environment & secrets

| Secret | Where | Purpose |
|---|---|---|
| `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_AUTH_KEY` (`.p8` file) | Backend (Railway) | Sign APNs requests |
| `FCM_SERVICE_ACCOUNT_JSON` | Backend (Railway) | Sign FCM v1 requests |
| `MATCH_PASSWORD`, `APP_STORE_CONNECT_KEY` | GitHub Secrets | iOS CI signing |
| `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD` | GitHub Secrets | Android CI signing |

`.env.example` updates in `backend/` and a new `mobile/.env.example`.

### 8.6 App metadata

- Bundle ID / app ID: `hk.ust.meli`.
- Display name: `Meli`.
- Icons: 1024×1024 master → all platform sizes via `npx cap-assets generate`.
- Splash screen: same source, same generator.
- **Privacy manifest** (`PrivacyInfo.xcprivacy`, required by Apple since 2024): declares mic usage, push token storage, audio file uploads.
- **iOS permission strings** (`Info.plist`):
  - `NSMicrophoneUsageDescription`: "Meli uses the microphone to score your pronunciation practice."
  - `NSCameraUsageDescription`: "Meli uses the camera to scan documents you upload to your courses."

### 8.7 Backend infra changes summary

- 3 new tables (one Alembic migration).
- ~10 new endpoints.
- 1 new service (`notifier.py`).
- 2 new external SDKs (apns2, firebase-admin).
- 2 new env var groups (APNs, FCM).
- CORS allow-list adds `capacitor://localhost` and `http://localhost`.

**No breaking changes. No existing endpoint touched.**

### 8.8 Frontend additions summary

- 3 new Next.js routes: `/dashboard/notifications`, `/dashboard/settings/reminders`, `/dashboard/courses/:cid/announcements/new`.
- 1 new component: notification bell + badge in nav.
- 1 small Capacitor detection helper: `frontend/src/lib/capacitor.ts` exports `isNative()` (used to suppress browser-only chrome inside the app, route deep links via `router.push` instead of `window.location.href`).
- Same `proxy.ts`, same Clerk middleware, same `tokens.css`.

---

## 9. Testing strategy

| Layer | What | Tooling |
|---|---|---|
| WebView (Next.js) | Unchanged tests + new `isNative()` paths | Existing Playwright + Capacitor mock for `isNative=true` |
| Native pronunciation (Swift) | Unit tests on audio buffer/format conversion; XCUITest for screen open/close | XCTest |
| Native pronunciation (Kotlin) | Unit tests on `AudioRecord` wrapper; Espresso for screen open/close + token receipt | JUnit + Espresso |
| Native flashcards (Swift) | Snapshot tests for card stack at various drag positions | XCTest + iOSSnapshotTestCase |
| Native flashcards (Kotlin) | Compose UI tests for swipe gestures; haptic stub | Compose Test + Robolectric |
| Push integration | "Send → device receives → tap → deep-links" | `xcrun simctl push` (iOS) + `adb shell am broadcast` (Android), automated for simulator path |
| Backend notifier | Unit tests with mocked APNs/FCM clients; integration test for de-dup + throttling | pytest |
| Cross-platform smoke | TestFlight + Play Internal build → real device walkthrough weekly | Manual checklist (~20 min) |

**Coverage targets:** 80% for new backend code. 60% line coverage for native code (UI dominated, better validated via snapshots and manual device passes).

**Device matrix for manual passes:**

- iOS: recent iPhone, older iPhone (2020-era), iPad.
- Android: Pixel, Samsung mid-range, low-end OEM.

---

## 10. Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| App Store rejects under "thin client wrapper" guideline 4.2 | Medium | Privacy manifest done correctly day 1; submission screenshots feature pronunciation + flashcards prominently; native push integration is real not decorative. |
| Clerk OAuth deep-link breaks on a future Clerk update | Low-Medium | Pin Clerk SDK version in WebView; smoke-test OAuth round-trip on every TestFlight build before promoting to public. |
| iOS WebView session loss after extended background | Low | Capacitor handles cookie persistence; default `WKWebsiteDataStore` already correct. Verify on real device after 7d background. |
| Audio capture quality differs across devices | Medium | Capture at 48 kHz, downsample to 16 kHz mono in our code (don't rely on device defaults). Test on the device matrix. |
| APNs / FCM tokens churn on reinstall/restore | High (normal) | `notification_devices.push_token` unique; new registrations upsert; 410-Gone responses delete. |
| Notification spam during dev/staging | Medium | Notifier service `if env != 'production': log_only()` toggle. |
| Apple Developer account approval delay for HKUST org | Low-Medium | Use individual developer account first → TestFlight while org account is approved. Transfer later (Apple supports this). |
| WebView keyboard pushes layout weirdly on iOS | Medium | Capacitor keyboard plugin + `viewport-fit=cover` + `env(safe-area-inset-bottom)` (already in global CSS) handles it; budget half a day for keyboard QA. |
| Native screen → WebView state desync | Medium | After native close, WebView always invalidates relevant TanStack Query keys. One line per native screen. |
| Two-codebase drift for tokens / API types | Low | tokens.json + types.ts codegen runs in CI; build fails on stale native files. |
| Live-quiz timer + push race condition | Low | `pushNotificationReceived` listener checks current route; suppresses in-app banner if quiz is active. |

---

## 11. Phased timeline (small team, 1-2 engineers)

```
Week 1-2   Foundation
           - mobile/ project scaffolded (npx @capacitor/cli init)
           - capacitor.config.ts + iOS/Android projects generated
           - Tokens codegen script + first build
           - WebView loads prod Next.js, signs in via Clerk + OAuth
           - Custom URL scheme deep links wired
           - First TestFlight + Play Internal build, internal team installs

Week 3-4   Backend notification system
           - Migration: notification_devices, notifications, announcements
           - notifier.py service
           - APNs + FCM clients
           - 10 new endpoints
           - Existing call-sites (live quiz start, async generation) wired
           - Throttling/batching worker

Week 5     Frontend notification UX (in WebView)
           - /dashboard/notifications feed
           - /dashboard/settings/reminders
           - /dashboard/courses/:cid/announcements/new (instructor)
           - Bell + badge in nav
           - Capacitor push wiring + cold-start deep link

Week 6-7   Native pronunciation (parallel iOS/Android)
           - Swift: AVAudioEngine + waveform
           - Kotlin: AudioRecord + waveform
           - Plugin bridge → token in, result out
           - On native, /dashboard/courses/:cid/pronunciation detects isNative() and calls App.openNative({screen:'pronunciation', ...}) instead of rendering the web UI
           - 6-device manual pass

Week 8-9   Native flashcards (parallel iOS/Android)
           - Swift: SwiftUI card stack + drag + CoreHaptics
           - Kotlin: Compose card stack + draggable + VibrationEffect
           - Plugin bridge
           - On native, /dashboard/courses/:cid/revision detects isNative() and calls App.openNative({screen:'flashcards', ...}). Flashcard-set study (/dashboard/courses/:cid/flashcards/:setId) stays in WebView for v1.
           - 6-device manual pass

Week 10    Polish & store assets
           - Icons, splash, privacy manifest
           - 5 screenshots per platform
           - App Privacy questionnaire
           - Marketing copy
           - Final TestFlight build → expand pilot to ~50 students

Week 11-12 Pilot + bug fixes
           - 2 weeks real student usage on real devices
           - Fix what they hit
           - Submit to App Store + Play Store for public listing
           - Apple review ~24-48hr, Google ~few hours

Total: ~12 weeks (3 months) with 2 engineers
```

If 1 engineer + product owner: multiply by ~1.6 → ~5 months.

---

## 12. Open questions to resolve before implementation planning

1. **App icon design.** Existing asset, or fresh design? (Placeholder OK until week 10.)
2. **Production domain.** Is `meli.app` real, or still a Vercel preview URL? Custom domain affects Clerk OAuth callback config and any future universal-link upgrade.
3. **Apple Developer enrollment.** Individual or HKUST org? Org enrolment requires D-U-N-S verification (~2 weeks); start now if pursuing.
4. **Pronunciation backend readiness.** Confirmed: `app/api/speech.py` already exposes `POST /api/speech/grade`, `POST /api/speech/generate-prompts`, and `GET /api/speech/courses/{course_id}/pronunciation-history`. Native screen uses these directly. **No new pronunciation endpoints required.** Same for flashcard review (`app/api/revision.py` revision-session endpoints exist).
5. **Designer involvement.** Native screens (especially flashcards swipe physics + haptic timing) benefit from a designer. On-team or engineers designing?

These don't block the spec; they feed into the implementation plan.

---

## 13. Success criteria

The mobile app is a success when:

1. ≥80% of pilot students complete onboarding (sign-in + first flashcard session) within their first 24 hours.
2. Pronunciation session completion rate on mobile ≥ web baseline (no regression).
3. Median time-to-first-card-rated < 10s in native flashcard screen (cold start to first interactive).
4. Live-quiz invite push delivery rate ≥ 95% within 30s of instructor session start (measured via `delivered_at` + client ack).
5. App Store rating ≥ 4.0 average across both platforms within 8 weeks of public listing.
6. App crashes (per session) < 0.5% across the device matrix in pilot.
7. Zero P1 (data-loss, auth-broken, payments-broken) bugs in pilot.

---

## 14. Out of scope (deferred decisions)

- Tablet-optimised layouts.
- Apple Watch / Wear OS companion.
- Offline parity (re-evaluate after pilot data).
- Native quiz player (currently fine in WebView).
- Native live-quiz screen (push + WebView is sufficient).
- Localization beyond English + Traditional Chinese (already in web).
- In-app purchases / subscriptions.
- Widget extensions (iOS home-screen widgets, Android app widgets).
- Siri / Google Assistant integration.
