# Plan E: Native Flashcard Review Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the WebView revision (mixed flashcard review) screen on native with a SwiftUI / Compose card-stack experience: smooth swipe gestures, haptic feedback per rating, native spring physics. The existing `app/api/revision.py` revision-session API drives all data flow — no new endpoints.

**Architecture:** A second Capacitor plugin (`Flashcards`) opens a full-screen native view. The WebView passes `{ token, courseId, difficulty?, mode? }` and gets back `{ cardsReviewed, sessionStats, xpAwarded }` on close. Native screen drives:
1. `POST /api/courses/{cid}/revision/start` → first item, session id
2. `GET /api/revision/sessions/{sid}/next` → fetch ahead-of-time
3. `POST /api/revision/sessions/{sid}/answer` per swipe rating
4. `POST /api/revision/sessions/{sid}/end` on close

**Tech Stack:**
- iOS: Swift 5.9, SwiftUI ZStack-based card stack, `DragGesture`, `CoreHaptics`.
- Android: Kotlin 1.9, Jetpack Compose `Box` with `Modifier.pointerInput` + `detectDragGestures`, `Animatable` for spring physics, `VibratorManager` for haptics.

**Spec reference:** `docs/superpowers/specs/2026-04-26-mobile-app-design.md` §6.2.

**Depends on Plan A** (Capacitor scaffold, plugin infrastructure, design tokens). Independent of Plans B, C, D.

---

## File Structure

```
mobile/
├── shared/types.ts                                       MOD: add FlashcardsParams, FlashcardsResult
├── ios/App/App/Plugins/
│   ├── FlashcardsPlugin.swift                            NEW: plugin entry
│   ├── FlashcardsPlugin.m                                NEW: ObjC bridge
│   ├── FlashcardsViewController.swift                    NEW: SwiftUI host
│   └── Flashcards/
│       ├── FlashcardsView.swift                          NEW: SwiftUI top-level view
│       ├── FlashcardsViewModel.swift                     NEW: state holder + API calls
│       ├── CardStackView.swift                           NEW: ZStack with drag gesture
│       ├── CardView.swift                                NEW: front/back of one card
│       ├── HapticPlayer.swift                            NEW: CoreHaptics wrapper
│       └── RevisionAPI.swift                             NEW: thin client for /api/revision
└── android/app/src/main/java/hk/ust/meli/
    └── flashcards/
        ├── FlashcardsPlugin.kt                           NEW: plugin entry
        ├── FlashcardsActivity.kt                         NEW: Compose host
        ├── FlashcardsViewModel.kt                        NEW: state holder
        ├── CardStack.kt                                  NEW: composable
        ├── HapticController.kt                           NEW: VibratorManager wrapper
        └── RevisionApi.kt                                NEW: thin client

frontend/src/
├── lib/native/flashcards.ts                              NEW: TS wrapper
└── app/dashboard/courses/[courseId]/revision/
    └── page.tsx                                           MOD: detect isNative + open native
```

---

## Task E1: Plugin contract types and TS wrapper

**Files:**
- Modify: `mobile/shared/types.ts`
- Create: `frontend/src/lib/native/flashcards.ts`
- Test: `frontend/src/lib/native/flashcards.test.ts`

- [ ] **Step 1: Extend `mobile/shared/types.ts`**

Add to the file (preserve existing exports from Plans A and D):

```ts
// --- Flashcards (Plan E) ---

export interface FlashcardsParams {
  token: string;
  courseId: string;
  difficulty?: 'easy' | 'medium' | 'hard';  // pass-through to revision API
  mode?: string;                             // pass-through (e.g., 'mixed')
}

export interface FlashcardsResult {
  sessionId: string;
  cardsReviewed: number;
  averageScore: number;     // 0-1; aggregated server-side via /end
  xpAwarded: number;
  abandoned: boolean;
}
```

- [ ] **Step 2: Failing test for the TS wrapper**

`frontend/src/lib/native/flashcards.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { openFlashcards } from './flashcards';

afterEach(() => {
  delete (globalThis as any).Capacitor;
});

describe('openFlashcards', () => {
  it('rejects on web', async () => {
    await expect(openFlashcards({ token: 't', courseId: 'c' })).rejects.toThrow(/native/i);
  });

  it('forwards to plugin', async () => {
    const open = vi.fn(async () => ({
      sessionId: 's', cardsReviewed: 5, averageScore: 0.8, xpAwarded: 30, abandoned: false
    }));
    (globalThis as any).Capacitor = {
      isNativePlatform: () => true,
      getPlatform: () => 'ios',
      Plugins: { Flashcards: { open } },
    };
    const res = await openFlashcards({ token: 't', courseId: 'c', difficulty: 'medium' });
    expect(open).toHaveBeenCalledWith({ token: 't', courseId: 'c', difficulty: 'medium' });
    expect(res.cardsReviewed).toBe(5);
  });
});
```

- [ ] **Step 3: Implement `frontend/src/lib/native/flashcards.ts`**

```ts
import { isNative } from '@/lib/capacitor';

export interface FlashcardsParams {
  token: string;
  courseId: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  mode?: string;
}

export interface FlashcardsResult {
  sessionId: string;
  cardsReviewed: number;
  averageScore: number;
  xpAwarded: number;
  abandoned: boolean;
}

interface FlashcardsPlugin {
  open(params: FlashcardsParams): Promise<FlashcardsResult>;
}

interface CapacitorWithPlugins {
  isNativePlatform: () => boolean;
  Plugins?: { Flashcards?: FlashcardsPlugin };
}

export async function openFlashcards(params: FlashcardsParams): Promise<FlashcardsResult> {
  if (!isNative()) {
    throw new Error('Flashcards plugin is only available on native platforms');
  }
  const cap = (globalThis as { Capacitor?: CapacitorWithPlugins }).Capacitor;
  const plugin = cap?.Plugins?.Flashcards;
  if (!plugin) throw new Error('Flashcards plugin not registered');
  return await plugin.open(params);
}
```

- [ ] **Step 4: Run test**

```bash
cd frontend && npm test -- src/lib/native/flashcards
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobile/shared/types.ts frontend/src/lib/native/flashcards.ts frontend/src/lib/native/flashcards.test.ts
git commit -m "feat(mobile): flashcards plugin contract + TS wrapper"
```

---

## Task E2: iOS — Plugin shell

**Files:**
- Create: `mobile/ios/App/App/Plugins/FlashcardsPlugin.swift`
- Create: `mobile/ios/App/App/Plugins/FlashcardsPlugin.m`

- [ ] **Step 1: Write `FlashcardsPlugin.swift`**

```swift
import Foundation
import Capacitor
import UIKit

@objc(FlashcardsPlugin)
public class FlashcardsPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "FlashcardsPlugin"
    public let jsName = "Flashcards"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "open", returnType: CAPPluginReturnPromise),
    ]

    @objc func open(_ call: CAPPluginCall) {
        guard
            let token = call.getString("token"),
            let courseId = call.getString("courseId")
        else {
            call.reject("Missing required params: token, courseId")
            return
        }
        let difficulty = call.getString("difficulty")
        let mode = call.getString("mode")

        DispatchQueue.main.async { [weak self] in
            guard let self, let bridgeViewController = self.bridge?.viewController else {
                call.reject("No host view controller")
                return
            }
            let vc = FlashcardsViewController(
                params: .init(token: token, courseId: courseId, difficulty: difficulty, mode: mode),
                onComplete: { result in
                    call.resolve([
                        "sessionId": result.sessionId,
                        "cardsReviewed": result.cardsReviewed,
                        "averageScore": result.averageScore,
                        "xpAwarded": result.xpAwarded,
                        "abandoned": result.abandoned,
                    ])
                }
            )
            vc.modalPresentationStyle = .fullScreen
            bridgeViewController.present(vc, animated: true)
        }
    }
}

struct FlashcardsParamsModel {
    let token: String
    let courseId: String
    let difficulty: String?
    let mode: String?
}

struct FlashcardsOutcome {
    let sessionId: String
    let cardsReviewed: Int
    let averageScore: Double
    let xpAwarded: Int
    let abandoned: Bool
}
```

- [ ] **Step 2: Write `FlashcardsPlugin.m`**

```objc
#import <Foundation/Foundation.h>
#import <Capacitor/Capacitor.h>

CAP_PLUGIN(FlashcardsPlugin, "Flashcards",
    CAP_PLUGIN_METHOD(open, CAPPluginReturnPromise);
)
```

- [ ] **Step 3: Add to Xcode and build**

(Add files to "Plugins" group, target App checked. ⌘B to verify the file compiles in isolation — `FlashcardsViewController` is defined next.)

- [ ] **Step 4: Commit**

```bash
git add mobile/ios/App/App/Plugins/FlashcardsPlugin.swift mobile/ios/App/App/Plugins/FlashcardsPlugin.m
git commit -m "feat(mobile-ios): Flashcards plugin entrypoint"
```

---

## Task E3: iOS — RevisionAPI client

**Files:**
- Create: `mobile/ios/App/App/Plugins/Flashcards/RevisionAPI.swift`

- [ ] **Step 1: Write the client**

```swift
import Foundation

struct RevisionAPI {
    let baseURL: URL  // https://meli.app/api
    let token: String

    enum APIError: Error {
        case http(Int, String)
        case decoding(Error)
        case transport(Error)
    }

    struct StartResponse: Decodable {
        let session_id: String
        let first_item: RevisionItem?
        let total_items: Int
    }

    struct NextResponse: Decodable {
        let item: RevisionItem?
        let remaining: Int
    }

    struct AnswerResponse: Decodable {
        let correct: Bool?
        let xp_awarded: Int?
    }

    struct EndResponse: Decodable {
        struct Stats: Decodable { let cardsReviewed: Int; let averageScore: Double }
        let stats: Stats
        let xp_awarded: Int
    }

    struct RevisionItem: Decodable, Identifiable {
        let id: String
        let prompt: String
        let answer: String
        let content_type: String
        let metadata: [String: String]?
    }

    private struct Envelope<T: Decodable>: Decodable {
        let success: Bool
        let data: T?
        let error: String?
    }

    func start(courseId: String, difficulty: String?, mode: String?) async throws -> StartResponse {
        let url = baseURL.appendingPathComponent("courses/\(courseId)/revision/start")
        var body: [String: String] = [:]
        if let d = difficulty { body["difficulty"] = d }
        if let m = mode { body["mode"] = m }
        return try await postJSON(url: url, body: body)
    }

    func next(sessionId: String) async throws -> NextResponse {
        let url = baseURL.appendingPathComponent("revision/sessions/\(sessionId)/next")
        return try await getJSON(url: url)
    }

    func answer(sessionId: String, itemId: String, rating: Int, responseTimeMs: Int) async throws -> AnswerResponse {
        let url = baseURL.appendingPathComponent("revision/sessions/\(sessionId)/answer")
        let body: [String: Any] = [
            "item_id": itemId, "rating": rating, "response_time_ms": responseTimeMs,
        ]
        return try await postJSON(url: url, body: body)
    }

    func end(sessionId: String) async throws -> EndResponse {
        let url = baseURL.appendingPathComponent("revision/sessions/\(sessionId)/end")
        return try await postJSON(url: url, body: [String: String]())
    }

    // MARK: -

    private func getJSON<T: Decodable>(url: URL) async throws -> T {
        var req = URLRequest(url: url)
        req.httpMethod = "GET"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        return try await execute(req)
    }

    private func postJSON<T: Decodable>(url: URL, body: Any) async throws -> T {
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
        return try await execute(req)
    }

    private func execute<T: Decodable>(_ req: URLRequest) async throws -> T {
        let data: Data, response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: req)
        } catch {
            throw APIError.transport(error)
        }
        guard let http = response as? HTTPURLResponse else { throw APIError.http(-1, "no response") }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
        }
        do {
            let env = try JSONDecoder().decode(Envelope<T>.self, from: data)
            guard env.success, let payload = env.data else {
                throw APIError.http(http.statusCode, env.error ?? "API error")
            }
            return payload
        } catch let e as DecodingError {
            throw APIError.decoding(e)
        }
    }
}
```

- [ ] **Step 2: Add to Xcode and build**

- [ ] **Step 3: Commit**

```bash
git add mobile/ios/App/App/Plugins/Flashcards/RevisionAPI.swift
git commit -m "feat(mobile-ios): RevisionAPI client for /api/revision endpoints"
```

---

## Task E4: iOS — Haptic player

**Files:**
- Create: `mobile/ios/App/App/Plugins/Flashcards/HapticPlayer.swift`

- [ ] **Step 1: Write the haptic player**

```swift
import CoreHaptics
import UIKit

/// Plays one-shot haptics keyed by rating intensity.
/// Falls back to UIImpactFeedbackGenerator on devices without haptic engine support.
final class HapticPlayer {
    enum Intensity { case light, medium, heavy }
    private var engine: CHHapticEngine?

    init() {
        guard CHHapticEngine.capabilitiesForHardware().supportsHaptics else { return }
        do {
            engine = try CHHapticEngine()
            try engine?.start()
            engine?.resetHandler = { [weak self] in try? self?.engine?.start() }
            engine?.stoppedHandler = { _ in }
        } catch {
            engine = nil
        }
    }

    func play(_ intensity: Intensity) {
        if let engine {
            playWithEngine(intensity, engine: engine)
        } else {
            playFallback(intensity)
        }
    }

    private func playWithEngine(_ intensity: Intensity, engine: CHHapticEngine) {
        let amp: Float = switch intensity {
            case .light: 0.4
            case .medium: 0.7
            case .heavy: 1.0
        }
        let event = CHHapticEvent(
            eventType: .hapticTransient,
            parameters: [
                CHHapticEventParameter(parameterID: .hapticIntensity, value: amp),
                CHHapticEventParameter(parameterID: .hapticSharpness, value: 0.5),
            ],
            relativeTime: 0
        )
        do {
            let pattern = try CHHapticPattern(events: [event], parameters: [])
            let player = try engine.makePlayer(with: pattern)
            try player.start(atTime: 0)
        } catch {
            playFallback(intensity)
        }
    }

    private func playFallback(_ intensity: Intensity) {
        let style: UIImpactFeedbackGenerator.FeedbackStyle = switch intensity {
            case .light: .light
            case .medium: .medium
            case .heavy: .heavy
        }
        let gen = UIImpactFeedbackGenerator(style: style)
        gen.impactOccurred()
    }
}
```

- [ ] **Step 2: Add and build, commit**

```bash
git add mobile/ios/App/App/Plugins/Flashcards/HapticPlayer.swift
git commit -m "feat(mobile-ios): CoreHaptics player with UIImpactFeedback fallback"
```

---

## Task E5: iOS — ViewModel and Card UI

**Files:**
- Create: `mobile/ios/App/App/Plugins/Flashcards/FlashcardsViewModel.swift`
- Create: `mobile/ios/App/App/Plugins/Flashcards/CardView.swift`
- Create: `mobile/ios/App/App/Plugins/Flashcards/CardStackView.swift`
- Create: `mobile/ios/App/App/Plugins/Flashcards/FlashcardsView.swift`
- Create: `mobile/ios/App/App/Plugins/FlashcardsViewController.swift`

- [ ] **Step 1: Write the view model**

```swift
import Foundation
import SwiftUI

@MainActor
final class FlashcardsViewModel: ObservableObject {
    enum Phase: Equatable {
        case loading
        case ready
        case finished(outcome: FlashcardsOutcome)
        case error(String)
    }

    @Published private(set) var phase: Phase = .loading
    @Published private(set) var queue: [RevisionAPI.RevisionItem] = []
    @Published var revealed: Bool = false
    @Published var dragOffset: CGSize = .zero

    private let params: FlashcardsParamsModel
    private let api: RevisionAPI
    private let haptics = HapticPlayer()
    private var sessionId: String?
    private var cardStartTime: Date?
    private var cardsRated = 0
    private var totalRemaining: Int = 0

    init(params: FlashcardsParamsModel) {
        self.params = params
        self.api = RevisionAPI(
            baseURL: URL(string: params.serverBase)!.appendingPathComponent("api"),
            token: params.token
        )
    }

    func bootstrap() async {
        do {
            let r = try await api.start(courseId: params.courseId, difficulty: params.difficulty, mode: params.mode)
            sessionId = r.session_id
            totalRemaining = r.total_items
            if let first = r.first_item {
                queue = [first]
                await prefetch(2)
                cardStartTime = Date()
                phase = .ready
            } else {
                await close(abandoned: false)
            }
        } catch {
            phase = .error(error.localizedDescription)
        }
    }

    private func prefetch(_ count: Int) async {
        guard let sid = sessionId else { return }
        for _ in 0..<count {
            do {
                let r = try await api.next(sessionId: sid)
                if let it = r.item { queue.append(it) }
                totalRemaining = r.remaining
                if r.item == nil { break }
            } catch {
                break
            }
        }
    }

    /// Rating: 0=Again (Hard), 1=Good, 2=Easy. Backend translates.
    func rate(_ rating: Int) async {
        guard let sid = sessionId, let card = queue.first else { return }
        let elapsed = Int((cardStartTime?.timeIntervalSinceNow ?? 0) * -1000)
        haptics.play(rating == 0 ? .heavy : rating == 1 ? .medium : .light)
        cardsRated += 1
        revealed = false
        dragOffset = .zero
        queue.removeFirst()
        if queue.count < 2 { Task { await prefetch(2) } }
        cardStartTime = Date()
        do {
            _ = try await api.answer(
                sessionId: sid, itemId: card.id, rating: rating, responseTimeMs: max(0, elapsed)
            )
        } catch {
            // Retry once silently; if still fails, log & continue.
            try? await Task.sleep(nanoseconds: 250_000_000)
            _ = try? await api.answer(
                sessionId: sid, itemId: card.id, rating: rating, responseTimeMs: max(0, elapsed)
            )
        }
        if queue.isEmpty && totalRemaining == 0 {
            await close(abandoned: false)
        }
    }

    func reveal() { revealed.toggle() }

    func close(abandoned: Bool) async {
        guard let sid = sessionId else {
            phase = .finished(outcome: FlashcardsOutcome(
                sessionId: "", cardsReviewed: cardsRated, averageScore: 0, xpAwarded: 0,
                abandoned: abandoned || cardsRated == 0
            ))
            return
        }
        do {
            let r = try await api.end(sessionId: sid)
            phase = .finished(outcome: FlashcardsOutcome(
                sessionId: sid, cardsReviewed: r.stats.cardsReviewed,
                averageScore: r.stats.averageScore, xpAwarded: r.xp_awarded,
                abandoned: abandoned && cardsRated == 0
            ))
        } catch {
            phase = .finished(outcome: FlashcardsOutcome(
                sessionId: sid, cardsReviewed: cardsRated, averageScore: 0, xpAwarded: 0,
                abandoned: abandoned || cardsRated == 0
            ))
        }
    }
}

private extension FlashcardsParamsModel {
    var serverBase: String {
        Bundle.main.object(forInfoDictionaryKey: "MELI_PROD_URL") as? String ?? "https://meli.app"
    }
}
```

- [ ] **Step 2: Write `CardView.swift`**

```swift
import SwiftUI

struct CardView: View {
    let prompt: String
    let answer: String
    let revealed: Bool

    var body: some View {
        VStack(spacing: 12) {
            Text(prompt)
                .font(.title2)
                .multilineTextAlignment(.center)
            Divider().opacity(revealed ? 1 : 0.2)
            if revealed {
                Text(answer)
                    .font(.title3)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(
            RoundedRectangle(cornerRadius: 24)
                .fill(Color(Tokens.surface))
                .shadow(color: .black.opacity(0.08), radius: 12, y: 4)
        )
    }
}
```

- [ ] **Step 3: Write `CardStackView.swift`**

```swift
import SwiftUI

struct CardStackView: View {
    @ObservedObject var vm: FlashcardsViewModel

    var body: some View {
        ZStack {
            // Render up to 3 cards with depth.
            ForEach(Array(vm.queue.prefix(3).enumerated().reversed()), id: \.element.id) { index, item in
                let depth = CGFloat(index)
                CardView(prompt: item.prompt, answer: item.answer, revealed: index == 0 && vm.revealed)
                    .scaleEffect(1 - depth * 0.04)
                    .offset(y: depth * 8)
                    .zIndex(Double(-depth))
                    .opacity(index == 0 ? 1 : 0.7)
                    .modifier(TopCardGesture(vm: vm, isTop: index == 0))
                    .animation(.interactiveSpring(response: 0.32, dampingFraction: 0.78), value: vm.dragOffset)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: 480)
    }
}

struct TopCardGesture: ViewModifier {
    @ObservedObject var vm: FlashcardsViewModel
    let isTop: Bool

    func body(content: Content) -> some View {
        if isTop {
            content
                .offset(vm.dragOffset)
                .rotationEffect(.degrees(Double(vm.dragOffset.width / 24)))
                .gesture(
                    DragGesture()
                        .onChanged { value in vm.dragOffset = value.translation }
                        .onEnded { value in
                            let threshold: CGFloat = 120
                            let dx = value.translation.width
                            let dy = value.translation.height
                            // Swipe up = Easy, right = Good, left = Again. Tap = reveal.
                            if abs(dx) < 8 && abs(dy) < 8 {
                                vm.reveal()
                                vm.dragOffset = .zero
                            } else if dy < -threshold {
                                vm.dragOffset = .init(width: 0, height: -1200)
                                Task { await vm.rate(2) }  // Easy
                            } else if dx > threshold {
                                vm.dragOffset = .init(width: 1200, height: dy)
                                Task { await vm.rate(1) }  // Good
                            } else if dx < -threshold {
                                vm.dragOffset = .init(width: -1200, height: dy)
                                Task { await vm.rate(0) }  // Again / Hard
                            } else {
                                vm.dragOffset = .zero
                            }
                        }
                )
        } else {
            content
        }
    }
}
```

- [ ] **Step 4: Write `FlashcardsView.swift`**

```swift
import SwiftUI

struct FlashcardsView: View {
    @StateObject var vm: FlashcardsViewModel
    let onClose: (FlashcardsOutcome) -> Void

    var body: some View {
        VStack(spacing: 16) {
            HStack {
                Button("Close") { Task { await vm.close(abandoned: true) } }
                Spacer()
            }.padding(.horizontal)

            switch vm.phase {
            case .loading:
                ProgressView().frame(maxHeight: .infinity)
            case .error(let m):
                Text(m).foregroundColor(.red).frame(maxHeight: .infinity)
            case .ready:
                CardStackView(vm: vm).padding(.horizontal, 20)
                ratingButtons
            case .finished(let o):
                Text("Done — \(o.cardsReviewed) cards").font(.title)
                    .onAppear { onClose(o) }
            }
        }
        .background(Color(Tokens.background).ignoresSafeArea())
        .task { await vm.bootstrap() }
    }

    private var ratingButtons: some View {
        HStack(spacing: 12) {
            ratingButton(label: "Again", color: .red) { Task { await vm.rate(0) } }
            ratingButton(label: "Good", color: .yellow) { Task { await vm.rate(1) } }
            ratingButton(label: "Easy", color: .green) { Task { await vm.rate(2) } }
        }.padding(.horizontal, 20).padding(.bottom, 24)
    }

    private func ratingButton(label: String, color: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label).font(.headline)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(color.opacity(0.85))
                .foregroundColor(.white)
                .cornerRadius(12)
        }
    }
}
```

- [ ] **Step 5: Write `FlashcardsViewController.swift`**

```swift
import SwiftUI
import UIKit

final class FlashcardsViewController: UIViewController {
    private let params: FlashcardsParamsModel
    private let onComplete: (FlashcardsOutcome) -> Void
    private var didReport = false

    init(params: FlashcardsParamsModel, onComplete: @escaping (FlashcardsOutcome) -> Void) {
        self.params = params
        self.onComplete = onComplete
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError() }

    override func viewDidLoad() {
        super.viewDidLoad()
        let vm = FlashcardsViewModel(params: params)
        let view = FlashcardsView(vm: vm) { [weak self] outcome in
            self?.report(outcome)
        }
        let host = UIHostingController(rootView: view)
        addChild(host)
        host.view.frame = self.view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        self.view.addSubview(host.view)
        host.didMove(toParent: self)
    }

    private func report(_ outcome: FlashcardsOutcome) {
        guard !didReport else { return }
        didReport = true
        dismiss(animated: true) { [weak self] in self?.onComplete(outcome) }
    }
}
```

- [ ] **Step 6: Add files to Xcode and build**

- [ ] **Step 7: Run on simulator (smoke test)**

The plugin won't fire until the WebView calls it (Task E7). For now, verify the build cleanly succeeds.

- [ ] **Step 8: Commit**

```bash
git add mobile/ios/App/App/Plugins/
git commit -m "feat(mobile-ios): flashcard review with card stack + drag gesture + haptics"
```

---

## Task E6: Android — Plugin shell, ViewModel, Compose UI

**Files:**
- Create: `mobile/android/app/src/main/java/hk/ust/meli/flashcards/FlashcardsPlugin.kt`
- Create: `mobile/android/app/src/main/java/hk/ust/meli/flashcards/FlashcardsActivity.kt`
- Create: `mobile/android/app/src/main/java/hk/ust/meli/flashcards/FlashcardsViewModel.kt`
- Create: `mobile/android/app/src/main/java/hk/ust/meli/flashcards/RevisionApi.kt`
- Create: `mobile/android/app/src/main/java/hk/ust/meli/flashcards/HapticController.kt`
- Create: `mobile/android/app/src/main/java/hk/ust/meli/flashcards/CardStack.kt`

- [ ] **Step 1: Plugin entrypoint**

```kotlin
package hk.ust.meli.flashcards

import android.content.Intent
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.ActivityCallback
import com.getcapacitor.annotation.CapacitorPlugin

@CapacitorPlugin(name = "Flashcards")
class FlashcardsPlugin : Plugin() {

    @PluginMethod
    fun open(call: PluginCall) {
        val token = call.getString("token") ?: return call.reject("Missing token")
        val courseId = call.getString("courseId") ?: return call.reject("Missing courseId")
        val intent = Intent(activity, FlashcardsActivity::class.java).apply {
            putExtra("token", token)
            putExtra("courseId", courseId)
            putExtra("difficulty", call.getString("difficulty"))
            putExtra("mode", call.getString("mode"))
        }
        startActivityForResult(call, intent, "flashcardsResult")
    }

    @ActivityCallback
    private fun flashcardsResult(call: PluginCall, result: androidx.activity.result.ActivityResult) {
        val data = result.data
        val res = JSObject().apply {
            put("sessionId", data?.getStringExtra("sessionId") ?: "")
            put("cardsReviewed", data?.getIntExtra("cardsReviewed", 0) ?: 0)
            put("averageScore", data?.getDoubleExtra("averageScore", 0.0) ?: 0.0)
            put("xpAwarded", data?.getIntExtra("xpAwarded", 0) ?: 0)
            put("abandoned", data?.getBooleanExtra("abandoned", true) ?: true)
        }
        call.resolve(res)
    }
}
```

- [ ] **Step 2: RevisionApi.kt**

```kotlin
package hk.ust.meli.flashcards

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

data class RevisionItem(val id: String, val prompt: String, val answer: String, val contentType: String)
data class StartResponse(val sessionId: String, val firstItem: RevisionItem?, val totalItems: Int)
data class NextResponse(val item: RevisionItem?, val remaining: Int)
data class EndResponse(val cardsReviewed: Int, val averageScore: Double, val xpAwarded: Int)

class RevisionApi(private val baseUrl: String, private val token: String) {
    private val client = OkHttpClient()

    suspend fun start(courseId: String, difficulty: String?, mode: String?): StartResponse =
        withContext(Dispatchers.IO) {
            val body = JSONObject().apply {
                difficulty?.let { put("difficulty", it) }
                mode?.let { put("mode", it) }
            }
            val req = Request.Builder()
                .url("$baseUrl/api/courses/$courseId/revision/start")
                .addHeader("Authorization", "Bearer $token")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()
            client.newCall(req).execute().use { resp ->
                require(resp.isSuccessful) { "start failed: ${resp.code}" }
                val data = JSONObject(resp.body!!.string()).getJSONObject("data")
                val firstItem = data.optJSONObject("first_item")?.let { o ->
                    RevisionItem(o.getString("id"), o.getString("prompt"),
                        o.getString("answer"), o.getString("content_type"))
                }
                StartResponse(
                    sessionId = data.getString("session_id"),
                    firstItem = firstItem,
                    totalItems = data.getInt("total_items"),
                )
            }
        }

    suspend fun next(sessionId: String): NextResponse = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url("$baseUrl/api/revision/sessions/$sessionId/next")
            .addHeader("Authorization", "Bearer $token")
            .get().build()
        client.newCall(req).execute().use { resp ->
            require(resp.isSuccessful) { "next failed: ${resp.code}" }
            val data = JSONObject(resp.body!!.string()).getJSONObject("data")
            val item = data.optJSONObject("item")?.let { o ->
                RevisionItem(o.getString("id"), o.getString("prompt"),
                    o.getString("answer"), o.getString("content_type"))
            }
            NextResponse(item, data.getInt("remaining"))
        }
    }

    suspend fun answer(sessionId: String, itemId: String, rating: Int, responseTimeMs: Int) {
        withContext(Dispatchers.IO) {
            val body = JSONObject().apply {
                put("item_id", itemId); put("rating", rating); put("response_time_ms", responseTimeMs)
            }
            val req = Request.Builder()
                .url("$baseUrl/api/revision/sessions/$sessionId/answer")
                .addHeader("Authorization", "Bearer $token")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()
            client.newCall(req).execute().close()
        }
    }

    suspend fun end(sessionId: String): EndResponse = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url("$baseUrl/api/revision/sessions/$sessionId/end")
            .addHeader("Authorization", "Bearer $token")
            .post(JSONObject().toString().toRequestBody("application/json".toMediaType()))
            .build()
        client.newCall(req).execute().use { resp ->
            require(resp.isSuccessful) { "end failed: ${resp.code}" }
            val data = JSONObject(resp.body!!.string()).getJSONObject("data")
            val stats = data.getJSONObject("stats")
            EndResponse(
                cardsReviewed = stats.getInt("cardsReviewed"),
                averageScore = stats.getDouble("averageScore"),
                xpAwarded = data.optInt("xp_awarded", 0),
            )
        }
    }
}
```

- [ ] **Step 3: HapticController.kt**

```kotlin
package hk.ust.meli.flashcards

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager

class HapticController(context: Context) {
    private val vibrator: Vibrator? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        val vm = context.getSystemService(VibratorManager::class.java)
        vm?.defaultVibrator
    } else {
        @Suppress("DEPRECATION")
        context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
    }

    enum class Intensity { LIGHT, MEDIUM, HEAVY }

    fun play(intensity: Intensity) {
        val v = vibrator ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val effect = when (intensity) {
                Intensity.LIGHT -> VibrationEffect.createPredefined(VibrationEffect.EFFECT_TICK)
                Intensity.MEDIUM -> VibrationEffect.createPredefined(VibrationEffect.EFFECT_CLICK)
                Intensity.HEAVY -> VibrationEffect.createPredefined(VibrationEffect.EFFECT_HEAVY_CLICK)
            }
            v.vibrate(effect)
        } else {
            @Suppress("DEPRECATION")
            v.vibrate(when (intensity) {
                Intensity.LIGHT -> 20L
                Intensity.MEDIUM -> 50L
                Intensity.HEAVY -> 100L
            })
        }
    }
}
```

- [ ] **Step 4: ViewModel**

```kotlin
package hk.ust.meli.flashcards

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface FlashcardsPhase {
    data object Loading : FlashcardsPhase
    data object Ready : FlashcardsPhase
    data class Finished(val outcome: FlashcardsOutcome) : FlashcardsPhase
    data class Error(val message: String) : FlashcardsPhase
}

data class FlashcardsOutcome(
    val sessionId: String,
    val cardsReviewed: Int,
    val averageScore: Double,
    val xpAwarded: Int,
    val abandoned: Boolean,
)

class FlashcardsViewModel(
    private val token: String,
    private val courseId: String,
    private val difficulty: String?,
    private val mode: String?,
    private val api: RevisionApi,
    private val haptics: HapticController,
) : ViewModel() {
    private val _phase = MutableStateFlow<FlashcardsPhase>(FlashcardsPhase.Loading)
    val phase: StateFlow<FlashcardsPhase> = _phase.asStateFlow()

    private val _queue = MutableStateFlow<List<RevisionItem>>(emptyList())
    val queue: StateFlow<List<RevisionItem>> = _queue.asStateFlow()

    private val _revealed = MutableStateFlow(false)
    val revealed: StateFlow<Boolean> = _revealed.asStateFlow()

    private var sessionId: String = ""
    private var totalRemaining = 0
    private var cardStartTime: Long = 0
    private var cardsRated = 0

    fun bootstrap() {
        viewModelScope.launch {
            try {
                val r = api.start(courseId, difficulty, mode)
                sessionId = r.sessionId
                totalRemaining = r.totalItems
                if (r.firstItem != null) {
                    _queue.value = listOf(r.firstItem)
                    prefetch(2)
                    cardStartTime = System.currentTimeMillis()
                    _phase.value = FlashcardsPhase.Ready
                } else {
                    end(false)
                }
            } catch (t: Throwable) {
                _phase.value = FlashcardsPhase.Error(t.message ?: "start failed")
            }
        }
    }

    private suspend fun prefetch(n: Int) {
        for (i in 0 until n) {
            try {
                val r = api.next(sessionId)
                if (r.item != null) _queue.value = _queue.value + r.item
                totalRemaining = r.remaining
                if (r.item == null) break
            } catch (_: Throwable) { break }
        }
    }

    fun reveal() { _revealed.value = !_revealed.value }

    fun rate(rating: Int) {
        viewModelScope.launch {
            val current = _queue.value.firstOrNull() ?: return@launch
            val elapsed = (System.currentTimeMillis() - cardStartTime).toInt()
            haptics.play(when (rating) { 0 -> HapticController.Intensity.HEAVY
                1 -> HapticController.Intensity.MEDIUM else -> HapticController.Intensity.LIGHT })
            cardsRated++
            _revealed.value = false
            _queue.value = _queue.value.drop(1)
            if (_queue.value.size < 2) prefetch(2)
            cardStartTime = System.currentTimeMillis()
            try {
                api.answer(sessionId, current.id, rating, elapsed.coerceAtLeast(0))
            } catch (_: Throwable) {
                // best-effort retry
                try { api.answer(sessionId, current.id, rating, elapsed.coerceAtLeast(0)) }
                catch (_: Throwable) {}
            }
            if (_queue.value.isEmpty() && totalRemaining == 0) end(false)
        }
    }

    fun end(abandoned: Boolean) {
        viewModelScope.launch {
            val outcome = try {
                val r = api.end(sessionId)
                FlashcardsOutcome(sessionId, r.cardsReviewed, r.averageScore, r.xpAwarded, abandoned && cardsRated == 0)
            } catch (_: Throwable) {
                FlashcardsOutcome(sessionId, cardsRated, 0.0, 0, abandoned && cardsRated == 0)
            }
            _phase.value = FlashcardsPhase.Finished(outcome)
        }
    }
}
```

- [ ] **Step 5: CardStack.kt**

```kotlin
package hk.ust.meli.flashcards

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.spring
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import kotlin.math.absoluteValue
import hk.ust.meli.Tokens

@Composable
fun CardStack(
    queue: List<RevisionItem>,
    revealed: Boolean,
    onTap: () -> Unit,
    onRate: (Int) -> Unit,
) {
    val offsetX = remember { Animatable(0f) }
    val offsetY = remember { Animatable(0f) }
    val scope = rememberCoroutineScope()

    Box(modifier = Modifier.fillMaxWidth().height(440.dp), contentAlignment = Alignment.Center) {
        queue.take(3).withIndex().reversed().forEach { (index, item) ->
            val depth = index.toFloat()
            val isTop = index == 0
            Card(
                shape = RoundedCornerShape(20.dp),
                modifier = Modifier
                    .fillMaxWidth(0.86f)
                    .height(360.dp)
                    .graphicsLayer {
                        scaleX = 1f - depth * 0.04f
                        scaleY = 1f - depth * 0.04f
                        translationY = depth * 18f
                        translationX = if (isTop) offsetX.value else 0f
                        rotationZ = if (isTop) offsetX.value / 24f else 0f
                        if (isTop) translationY = translationY + offsetY.value
                        alpha = if (isTop) 1f else 0.7f
                    }
                    .pointerInput(item.id) {
                        if (!isTop) return@pointerInput
                        detectDragGestures(
                            onDragEnd = {
                                val dx = offsetX.value
                                val dy = offsetY.value
                                val threshold = 320f
                                when {
                                    dx.absoluteValue < 8f && dy.absoluteValue < 8f -> {
                                        onTap()
                                        scope.launch {
                                            offsetX.animateTo(0f); offsetY.animateTo(0f)
                                        }
                                    }
                                    dy < -threshold -> {
                                        scope.launch { offsetY.animateTo(-2400f, spring()) }
                                        onRate(2)
                                        scope.launch { offsetX.snapTo(0f); offsetY.snapTo(0f) }
                                    }
                                    dx > threshold -> {
                                        scope.launch { offsetX.animateTo(2400f, spring()) }
                                        onRate(1)
                                        scope.launch { offsetX.snapTo(0f); offsetY.snapTo(0f) }
                                    }
                                    dx < -threshold -> {
                                        scope.launch { offsetX.animateTo(-2400f, spring()) }
                                        onRate(0)
                                        scope.launch { offsetX.snapTo(0f); offsetY.snapTo(0f) }
                                    }
                                    else -> scope.launch {
                                        offsetX.animateTo(0f, spring())
                                        offsetY.animateTo(0f, spring())
                                    }
                                }
                            },
                            onDrag = { change, drag ->
                                change.consume()
                                scope.launch {
                                    offsetX.snapTo(offsetX.value + drag.x)
                                    offsetY.snapTo(offsetY.value + drag.y)
                                }
                            }
                        )
                    }
            ) {
                Column(
                    modifier = Modifier.fillMaxSize().padding(28.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.SpaceEvenly,
                ) {
                    Text(item.prompt, style = MaterialTheme.typography.headlineSmall)
                    if (isTop && revealed) {
                        Divider()
                        Text(item.answer, style = MaterialTheme.typography.titleMedium)
                    }
                }
            }
        }
    }
}
```

- [ ] **Step 6: FlashcardsActivity.kt**

```kotlin
package hk.ust.meli.flashcards

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider

class FlashcardsActivity : ComponentActivity() {
    private lateinit var vm: FlashcardsViewModel

    override fun onCreate(s: Bundle?) {
        super.onCreate(s)
        val token = intent.getStringExtra("token")!!
        val courseId = intent.getStringExtra("courseId")!!
        val difficulty = intent.getStringExtra("difficulty")
        val mode = intent.getStringExtra("mode")

        val baseUrl = applicationInfo.metaData?.getString("MELI_PROD_URL") ?: "https://meli.app"
        val api = RevisionApi(baseUrl, token)
        val haptics = HapticController(this)

        vm = ViewModelProvider(this, object : ViewModelProvider.Factory {
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                @Suppress("UNCHECKED_CAST")
                return FlashcardsViewModel(token, courseId, difficulty, mode, api, haptics) as T
            }
        })[FlashcardsViewModel::class.java]

        vm.bootstrap()

        setContent {
            MaterialTheme {
                FlashcardsScreen(vm = vm, onClose = {
                    vm.end(true)
                })
            }
        }

        // Listen for terminal phase to finish.
        lifecycleScope.launchWhenStarted {
            vm.phase.collect { p ->
                if (p is FlashcardsPhase.Finished) {
                    finishWith(p.outcome)
                }
            }
        }
    }

    private fun finishWith(outcome: FlashcardsOutcome) {
        val data = Intent().apply {
            putExtra("sessionId", outcome.sessionId)
            putExtra("cardsReviewed", outcome.cardsReviewed)
            putExtra("averageScore", outcome.averageScore)
            putExtra("xpAwarded", outcome.xpAwarded)
            putExtra("abandoned", outcome.abandoned)
        }
        setResult(Activity.RESULT_OK, data)
        finish()
    }
}

@Composable
fun FlashcardsScreen(vm: FlashcardsViewModel, onClose: () -> Unit) {
    val phase by vm.phase.collectAsState()
    val queue by vm.queue.collectAsState()
    val revealed by vm.revealed.collectAsState()

    Column(modifier = Modifier.fillMaxSize().padding(20.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            TextButton(onClick = onClose) { Text("Close") }
        }
        Spacer(Modifier.height(12.dp))

        when (val p = phase) {
            is FlashcardsPhase.Loading -> CircularProgressIndicator()
            is FlashcardsPhase.Error -> Text(p.message, color = MaterialTheme.colorScheme.error)
            is FlashcardsPhase.Ready -> {
                CardStack(
                    queue = queue,
                    revealed = revealed,
                    onTap = { vm.reveal() },
                    onRate = { rating -> vm.rate(rating) },
                )
                Spacer(Modifier.height(12.dp))
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { vm.rate(0) }, modifier = Modifier.weight(1f)) { Text("Again") }
                    Button(onClick = { vm.rate(1) }, modifier = Modifier.weight(1f)) { Text("Good") }
                    Button(onClick = { vm.rate(2) }, modifier = Modifier.weight(1f)) { Text("Easy") }
                }
            }
            is FlashcardsPhase.Finished -> {
                Text("Done — ${p.outcome.cardsReviewed} cards", style = MaterialTheme.typography.headlineSmall)
            }
        }
    }
}
```

- [ ] **Step 7: Register plugin and activity**

In `MainActivity.kt`:

```kotlin
import hk.ust.meli.flashcards.FlashcardsPlugin
// ...
override fun onCreate(s: Bundle?) {
    registerPlugin(FlashcardsPlugin::class.java)
    registerPlugin(hk.ust.meli.pronunciation.PronunciationPlugin::class.java)  // already added in Plan D
    super.onCreate(s)
}
```

In `AndroidManifest.xml`, inside `<application>`:

```xml
<activity
    android:name=".flashcards.FlashcardsActivity"
    android:exported="false"
    android:theme="@style/AppTheme.Translucent" />
```

- [ ] **Step 8: Build and run**

```bash
cd mobile/android && ./gradlew assembleDebug
```

- [ ] **Step 9: Commit**

```bash
git add mobile/android/
git commit -m "feat(mobile-android): flashcard review with card stack + drag + haptics"
```

---

## Task E7: WebView side — open native screen on `isNative()`

**Files:**
- Modify: `frontend/src/app/dashboard/courses/[courseId]/revision/page.tsx`

- [ ] **Step 1: Read the existing page**

```bash
cat frontend/src/app/dashboard/courses/[courseId]/revision/page.tsx 2>&1 | head -80
```

- [ ] **Step 2: Insert isNative short-circuit**

```tsx
'use client';
import { useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useApiToken } from '@/hooks/useApiToken';
import { isNative } from '@/lib/capacitor';
import { openFlashcards } from '@/lib/native/flashcards';
// (... existing imports)

export default function RevisionPage() {
  const router = useRouter();
  const { courseId } = useParams<{ courseId: string }>();
  const { getToken } = useApiToken();

  useEffect(() => {
    if (!isNative()) return;
    let alive = true;
    (async () => {
      const token = await getToken();
      if (!token || !alive) return;
      try {
        const result = await openFlashcards({ token, courseId });
        router.replace(`/dashboard/courses/${courseId}/revision`);
        // queryClient.invalidateQueries({ queryKey: ['revision', courseId] });
        // queryClient.invalidateQueries({ queryKey: ['streak'] });
        console.log('Flashcards result', result);
      } catch (e) {
        console.error('openFlashcards failed', e);
      }
    })();
    return () => { alive = false; };
  }, [courseId, getToken, router]);

  if (isNative()) {
    return <p className="p-6 text-muted-foreground">Opening flashcard review…</p>;
  }
  // existing web UI below
}
```

- [ ] **Step 3: Manual smoke test on TestFlight + Play Internal**

Tag (`mobile-v0.4.0`), wait for builds, install. Sign in, navigate to a course's revision route. Expected:
- Native screen opens
- First card visible, can tap to reveal answer
- Swipe left = "Again" → heavy haptic; right = "Good" → medium haptic; up = "Easy" → light haptic
- Buttons at bottom also work
- After last card: success screen, then auto-close → WebView shows updated streak/stats

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/dashboard/courses/[courseId]/revision/page.tsx
git commit -m "feat(frontend): redirect /revision to native flashcards on isNative()"
```

---

## Task E8: Tests

**Files:**
- Create: `mobile/ios/App/AppTests/FlashcardsViewModelTests.swift`
- Create: `mobile/android/app/src/test/java/hk/ust/meli/flashcards/FlashcardsViewModelTest.kt`

- [ ] **Step 1: iOS unit test**

```swift
import XCTest
@testable import App

final class FlashcardsViewModelTests: XCTestCase {

    @MainActor
    func testCloseWithNoSessionReturnsAbandoned() async {
        let vm = FlashcardsViewModel(params: FlashcardsParamsModel(
            token: "t", courseId: "c", difficulty: nil, mode: nil
        ))
        await vm.close(abandoned: true)
        if case .finished(let outcome) = vm.phase {
            XCTAssertTrue(outcome.abandoned)
            XCTAssertEqual(outcome.cardsReviewed, 0)
        } else {
            XCTFail("Expected finished phase")
        }
    }
}
```

- [ ] **Step 2: Android unit test**

```kotlin
package hk.ust.meli.flashcards

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class FlashcardsViewModelTest {

    @Test
    fun `bootstrap with no items finishes immediately`() = runTest {
        val api = mockk<RevisionApi> {
            coEvery { start(any(), any(), any()) } returns
                StartResponse(sessionId = "s", firstItem = null, totalItems = 0)
            coEvery { end(any()) } returns EndResponse(0, 0.0, 0)
        }
        val haptics = mockk<HapticController>(relaxed = true)
        val vm = FlashcardsViewModel("t", "c", null, null, api, haptics)
        vm.bootstrap()
        advanceUntilIdle()
        val p = vm.phase.value
        assertTrue("expected Finished, got $p", p is FlashcardsPhase.Finished)
    }
}
```

- [ ] **Step 3: Run tests**

iOS: ⌘U in Xcode.
Android:

```bash
cd mobile/android && ./gradlew testDebugUnitTest
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add mobile/ios/App/AppTests/FlashcardsViewModelTests.swift mobile/android/app/src/test/java/hk/ust/meli/flashcards/FlashcardsViewModelTest.kt
git commit -m "test(mobile): flashcards view model unit tests"
```

---

## Acceptance criteria for Plan E

- [ ] iOS: tapping the revision route inside the app opens a native card-stack screen
- [ ] Android: same
- [ ] Tap toggles answer reveal
- [ ] Swipe left = Again (heavy haptic), right = Good (medium), up = Easy (light)
- [ ] Three rating buttons at bottom also work as accessibility fallback
- [ ] Card stack shows depth (current + next + next-next), animates smoothly during drag
- [ ] Spring snap-back works when drag is below threshold
- [ ] Last card fly-off triggers session end → outcome returned to WebView
- [ ] Both unit-test suites pass
- [ ] No regression to the web revision page (still works in browser)
- [ ] Permission handling: no extra permissions needed (haptics + network + storage already declared)
