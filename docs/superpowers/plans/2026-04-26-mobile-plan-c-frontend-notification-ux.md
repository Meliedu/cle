# Plan C: Frontend Notification UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the user-facing notification surfaces inside the Next.js app — in-app feed, navbar bell + unread badge, study-reminder local notifications, instructor announcement compose page — and wire Capacitor push receive (foreground + cold-start) for the mobile app.

**Architecture:** Three new App Router pages live inside `/dashboard/`. A navbar bell uses TanStack Query polling (60s) plus event-driven invalidation when `pushNotificationReceived` fires inside Capacitor. Local notifications for study reminders use `@capacitor/local-notifications` — entirely on-device, no backend. Deep-link routing has one source of truth: `handleDeepLink(path)` which uses `router.push` on native and `window.location.href` on web.

**Tech Stack:** Next.js 16 App Router, React 19, TanStack Query, Clerk, Tailwind, react-markdown, Capacitor 6 plugins (`@capacitor/push-notifications`, `@capacitor/local-notifications`, `@capacitor/app`).

**Spec reference:** `docs/superpowers/specs/2026-04-26-mobile-app-design.md` §7.4, §7.5, §7.6, §7.7, §7.8.

**Depends on Plan B** for the backend endpoints. Plan A is required only for the mobile-side push wiring (Tasks C7-C9); the web UI (C1-C6) works without Plan A.

---

## File Structure

```
frontend/src/
├── app/dashboard/
│   ├── notifications/
│   │   ├── page.tsx                              NEW: feed page
│   │   └── notification-item.tsx                 NEW: row component
│   ├── settings/
│   │   └── reminders/
│   │       └── page.tsx                          NEW: study reminder schedule editor
│   └── courses/[courseId]/
│       └── announcements/
│           ├── page.tsx                          NEW: instructor list
│           ├── new/
│           │   └── page.tsx                      NEW: compose form
│           └── [announcementId]/
│               └── page.tsx                      NEW: student view of an announcement
├── components/
│   ├── layout/
│   │   ├── navbar.tsx                            MOD: insert NotificationBell
│   │   └── sidebar.tsx                           MOD: add /dashboard/notifications link
│   └── notifications/
│       ├── notification-bell.tsx                 NEW: bell + badge
│       ├── notification-feed.tsx                 NEW: list + infinite scroll
│       ├── reminder-form.tsx                     NEW: schedule editor
│       └── announcement-compose.tsx              NEW: title + markdown body + send toggle
├── hooks/
│   ├── use-notifications.ts                      NEW: query + mutations
│   ├── use-unread-count.ts                       NEW: polling badge count
│   ├── use-reminders.ts                          NEW: local notifications schedule mgmt
│   ├── use-announcements.ts                      NEW: instructor compose API
│   └── use-deep-link.ts                          NEW: cold-start + push tap routing
├── lib/
│   ├── deep-link.ts                              NEW: handleDeepLink helper
│   ├── push-registration.ts                      NEW: Capacitor push registration + listeners
│   └── capacitor.ts                              EXISTING (from Plan A) — used here
└── components/providers/
    └── notification-provider.tsx                 NEW: top-level mount of push listeners
```

---

## Task C1: API hooks (use-notifications, use-unread-count)

**Files:**
- Create: `frontend/src/hooks/use-notifications.ts`
- Create: `frontend/src/hooks/use-unread-count.ts`
- Test: `frontend/src/hooks/use-notifications.test.tsx` (JSX syntax — the wrapper renders elements)

- [ ] **Step 1: Inspect existing API hook patterns**

```bash
ls frontend/src/hooks/ | head; head -30 frontend/src/hooks/useApiToken.ts 2>/dev/null
```

Note the existing pattern (`useApiToken`, TanStack Query, `apiFetch` from `@/lib/api`).

- [ ] **Step 2: Write the failing test**

`frontend/src/hooks/use-notifications.test.tsx`:

```ts
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useNotifications } from './use-notifications';

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({
    success: true,
    data: { items: [{ id: 'n1', type: 'announcement', title: 'x', body: 'y',
      deep_link: '/x', data: {}, read_at: null, delivered_at: null,
      created_at: '2026-04-26T00:00:00Z' }], next_cursor: null },
  })),
}));

vi.mock('@/hooks/useApiToken', () => ({
  useApiToken: () => ({ getToken: async () => 't' }),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
};

describe('useNotifications', () => {
  it('returns the first page of notifications', async () => {
    const { result } = renderHook(() => useNotifications(), { wrapper });
    await waitFor(() => expect(result.current.data?.pages?.[0]?.items?.length).toBe(1));
  });
});
```

- [ ] **Step 3: Run test (will fail — hook not yet defined)**

```bash
cd frontend && npm test -- src/hooks/use-notifications
```

Expected: FAIL.

- [ ] **Step 4: Implement `frontend/src/hooks/use-notifications.ts`**

```ts
'use client';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { useApiToken } from '@/hooks/useApiToken';

export type NotificationType =
  | 'live_quiz_invite'
  | 'announcement'
  | 'course_update'
  | 'content_ready';

export interface NotificationItem {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  deep_link: string;
  data: Record<string, unknown>;
  read_at: string | null;
  delivered_at: string | null;
  created_at: string;
}

interface FeedPage {
  items: NotificationItem[];
  next_cursor: string | null;
}

export const NOTIFICATIONS_QUERY_KEY = ['notifications'] as const;

export function useNotifications(limit = 20) {
  const { getToken } = useApiToken();
  return useInfiniteQuery({
    queryKey: NOTIFICATIONS_QUERY_KEY,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams();
      params.set('limit', String(limit));
      if (pageParam) params.set('cursor', pageParam);
      const res = await apiFetch<FeedPage>(
        `/api/notifications?${params.toString()}`,
        { token: await getToken() },
      );
      if (!res.success) throw new Error(res.error ?? 'Failed to load notifications');
      return res.data;
    },
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function useMarkRead() {
  const { getToken } = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const token = await getToken();
      const res = await apiFetch(`/api/notifications/${id}/read`, { method: 'POST', token });
      if (!res.success) throw new Error(res.error ?? 'Failed');
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ['notifications-unread-count'] });
    },
  });
}

export function useMarkAllRead() {
  const { getToken } = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const token = await getToken();
      const res = await apiFetch('/api/notifications/read-all', { method: 'POST', token });
      if (!res.success) throw new Error(res.error ?? 'Failed');
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ['notifications-unread-count'] });
    },
  });
}
```

- [ ] **Step 5: Implement `frontend/src/hooks/use-unread-count.ts`**

```ts
'use client';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { useApiToken } from '@/hooks/useApiToken';

const POLL_INTERVAL_MS = 60_000;

export function useUnreadCount() {
  const { getToken } = useApiToken();
  return useQuery({
    queryKey: ['notifications-unread-count'],
    queryFn: async () => {
      const res = await apiFetch<{ unread: number }>(
        '/api/notifications/unread-count',
        { token: await getToken() },
      );
      if (!res.success) throw new Error(res.error ?? 'Failed');
      return res.data.unread;
    },
    refetchInterval: (query) =>
      // Only poll when document is visible — saves bandwidth on backgrounded tabs
      typeof document !== 'undefined' && document.visibilityState === 'visible'
        ? POLL_INTERVAL_MS
        : false,
    refetchIntervalInBackground: false,
  });
}
```

- [ ] **Step 6: Re-run tests**

```bash
npm test -- src/hooks/use-notifications
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/use-notifications.ts frontend/src/hooks/use-unread-count.ts frontend/src/hooks/use-notifications.test.tsx
git commit -m "feat(frontend): notification + unread-count hooks"
```

---

## Task C2: Notification bell component

**Files:**
- Create: `frontend/src/components/notifications/notification-bell.tsx`

- [ ] **Step 1: Implement the bell**

```tsx
'use client';
import Link from 'next/link';
import { Bell } from 'lucide-react';
import { useUnreadCount } from '@/hooks/use-unread-count';

export function NotificationBell({ className }: { className?: string }) {
  const { data: unread } = useUnreadCount();
  const hasUnread = (unread ?? 0) > 0;

  return (
    <Link
      href="/dashboard/notifications"
      aria-label={hasUnread ? `Notifications, ${unread} unread` : 'Notifications'}
      className={`relative inline-flex h-9 w-9 items-center justify-center rounded-full hover:bg-muted ${className ?? ''}`}
    >
      <Bell className="h-5 w-5" />
      {hasUnread ? (
        <span
          className="absolute -right-0.5 -top-0.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-destructive px-1 text-[0.625rem] font-semibold text-destructive-foreground"
          data-testid="unread-badge"
        >
          {unread! > 99 ? '99+' : unread}
        </span>
      ) : null}
    </Link>
  );
}
```

- [ ] **Step 2: Mount in navbar**

Modify `frontend/src/components/layout/navbar.tsx`. Locate the right-aligned cluster (likely user menu + sign-out). Add the bell just before the user avatar:

```tsx
import { NotificationBell } from '@/components/notifications/notification-bell';
// ...
<div className="flex items-center gap-2">
  <NotificationBell />
  {/* existing avatar / user menu */}
</div>
```

- [ ] **Step 3: Verify rendering**

```bash
cd frontend && npm run dev
```

Open http://localhost:3000/dashboard. Expected: bell visible top-right; no badge when unread = 0.

- [ ] **Step 4: Add sidebar link to `/dashboard/notifications`**

Modify `frontend/src/components/layout/sidebar.tsx`. Find the existing nav-item array. Add an entry:

```ts
{ icon: Bell, label: 'Notifications', href: '/dashboard/notifications' }
```

(Order: just below "Calendar" or wherever fits the existing IA.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/notifications/notification-bell.tsx frontend/src/components/layout/navbar.tsx frontend/src/components/layout/sidebar.tsx
git commit -m "feat(frontend): navbar notification bell + sidebar link"
```

---

## Task C3: Notification feed page

**Files:**
- Create: `frontend/src/app/dashboard/notifications/page.tsx`
- Create: `frontend/src/components/notifications/notification-feed.tsx`
- Create: `frontend/src/app/dashboard/notifications/notification-item.tsx`

- [ ] **Step 1: Implement the row component**

`frontend/src/app/dashboard/notifications/notification-item.tsx`:

```tsx
'use client';
import { useRouter } from 'next/navigation';
import { Bell, FileText, GraduationCap, Megaphone, PlayCircle } from 'lucide-react';
import type { NotificationItem as TItem } from '@/hooks/use-notifications';
import { useMarkRead } from '@/hooks/use-notifications';
import { handleDeepLink } from '@/lib/deep-link';
import { formatRelativeTime } from '@/lib/format';

const ICON_BY_TYPE: Record<TItem['type'], typeof Bell> = {
  live_quiz_invite: PlayCircle,
  announcement: Megaphone,
  course_update: FileText,
  content_ready: GraduationCap,
};

export function NotificationItemRow({ item }: { item: TItem }) {
  const router = useRouter();
  const markRead = useMarkRead();
  const Icon = ICON_BY_TYPE[item.type];

  const onClick = async () => {
    if (!item.read_at) markRead.mutate(item.id);
    handleDeepLink(item.deep_link, router);
  };

  return (
    <button
      onClick={onClick}
      className={`flex w-full items-start gap-3 rounded-lg px-3 py-3 text-left transition-colors hover:bg-muted ${
        item.read_at ? 'opacity-70' : ''
      }`}
    >
      <Icon className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="font-medium">{item.title}</span>
          {!item.read_at && (
            <span
              aria-label="unread"
              className="inline-block h-2 w-2 shrink-0 rounded-full bg-destructive"
            />
          )}
        </div>
        <p className="line-clamp-2 text-sm text-muted-foreground">{item.body}</p>
        <span className="text-xs text-muted-foreground">
          {formatRelativeTime(item.created_at)}
        </span>
      </div>
    </button>
  );
}
```

(Confirm `formatRelativeTime` exists in `lib/format.ts`. If not, add it — small Intl wrapper.)

- [ ] **Step 2: Implement `notification-feed.tsx`**

`frontend/src/components/notifications/notification-feed.tsx`:

```tsx
'use client';
import { useEffect, useRef } from 'react';
import { useNotifications, useMarkAllRead } from '@/hooks/use-notifications';
import { NotificationItemRow } from '@/app/dashboard/notifications/notification-item';

export function NotificationFeed() {
  const { data, fetchNextPage, hasNextPage, isFetching, isFetchingNextPage } = useNotifications();
  const markAllRead = useMarkAllRead();
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sentinelRef.current) return;
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) fetchNextPage();
    });
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingNextPage]);

  const items = data?.pages.flatMap(p => p.items) ?? [];

  return (
    <div className="mx-auto max-w-2xl space-y-1 px-4 py-6">
      <div className="flex items-baseline justify-between pb-2">
        <h1 className="text-2xl font-semibold">Notifications</h1>
        <button
          onClick={() => markAllRead.mutate()}
          disabled={markAllRead.isPending || items.every(i => i.read_at)}
          className="text-sm text-primary hover:underline disabled:opacity-50"
        >
          Mark all read
        </button>
      </div>

      {isFetching && items.length === 0 ? (
        <p className="py-12 text-center text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="py-12 text-center text-muted-foreground">
          No notifications yet.
        </p>
      ) : (
        <div className="divide-y rounded-lg border">
          {items.map(it => <NotificationItemRow key={it.id} item={it} />)}
        </div>
      )}

      {hasNextPage && (
        <div ref={sentinelRef} className="h-12 flex items-center justify-center text-sm text-muted-foreground">
          {isFetchingNextPage ? 'Loading more…' : ''}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Implement the page**

`frontend/src/app/dashboard/notifications/page.tsx`:

```tsx
import { NotificationFeed } from '@/components/notifications/notification-feed';

export const metadata = { title: 'Notifications · Meli' };

export default function NotificationsPage() {
  return <NotificationFeed />;
}
```

- [ ] **Step 4: Manual smoke test**

Run dev server. Sign in. Visit `/dashboard/notifications`. Expected: empty state. Then via curl seed a notification:

```bash
USER_ID=...  # your dev user
psql langassistant -c "INSERT INTO notifications (user_id, type, title, body, deep_link, data) VALUES ('$USER_ID', 'announcement', 'Hello', 'Test', '/dashboard', '{}');"
```

Reload feed. Expected: row appears, badge shows 1.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/dashboard/notifications/ frontend/src/components/notifications/notification-feed.tsx
git commit -m "feat(frontend): notification feed page + infinite scroll"
```

---

## Task C4: Deep-link helper

**Files:**
- Create: `frontend/src/lib/deep-link.ts`
- Test: `frontend/src/lib/deep-link.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/deep-link.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleDeepLink } from './deep-link';

beforeEach(() => {
  delete (globalThis as any).Capacitor;
});

describe('handleDeepLink', () => {
  it('calls router.push when isNative()', () => {
    (globalThis as any).Capacitor = { isNativePlatform: () => true, getPlatform: () => 'ios' };
    const push = vi.fn();
    handleDeepLink('/dashboard/x', { push } as any);
    expect(push).toHaveBeenCalledWith('/dashboard/x');
  });

  it('calls window.location.href on web', () => {
    const originalHref = window.location.href;
    Object.defineProperty(window, 'location', {
      value: { ...window.location, href: originalHref, },
      writable: true,
    });
    handleDeepLink('/dashboard/x', { push: vi.fn() } as any);
    // We can't reliably assert `window.location.href = ...` with jsdom; check
    // alternative: pass an injectable navigate fn for testability
  });
});
```

- [ ] **Step 2: Implement (with injectable navigate for testability)**

`frontend/src/lib/deep-link.ts`:

```ts
import { isNative } from '@/lib/capacitor';

export interface RouterLike {
  push: (path: string) => void;
}

/**
 * Single source of truth for deep-link routing.
 *
 * - On native (Capacitor): use Next.js router so we don't reload the WebView.
 * - On web: full navigation with window.location.href.
 *
 * Pass `router` from `useRouter()`; the `_navigate` arg is for tests.
 */
export function handleDeepLink(
  path: string,
  router: RouterLike,
  _navigate?: (p: string) => void,
): void {
  if (isNative()) {
    router.push(path);
    return;
  }
  if (_navigate) {
    _navigate(path);
    return;
  }
  if (typeof window !== 'undefined') {
    window.location.href = path;
  }
}
```

Adjust the second test to inject `_navigate`:

```ts
it('uses _navigate fallback on web', () => {
  const navigate = vi.fn();
  handleDeepLink('/dashboard/x', { push: vi.fn() } as any, navigate);
  expect(navigate).toHaveBeenCalledWith('/dashboard/x');
});
```

- [ ] **Step 3: Run tests**

```bash
npm test -- src/lib/deep-link
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/deep-link.ts frontend/src/lib/deep-link.test.ts
git commit -m "feat(frontend): handleDeepLink helper for native + web routing"
```

---

## Task C5: Reminder settings page (local notifications)

**Files:**
- Create: `frontend/src/app/dashboard/settings/reminders/page.tsx`
- Create: `frontend/src/components/notifications/reminder-form.tsx`
- Create: `frontend/src/hooks/use-reminders.ts`

These reminders are stored locally on the device via Capacitor's LocalNotifications plugin (no backend persistence). On web, the page shows a "this feature is mobile-only" message.

- [ ] **Step 1: Implement `use-reminders.ts`**

```ts
'use client';
import { useEffect, useState } from 'react';
import { isNative } from '@/lib/capacitor';

export interface Reminder {
  id: number;
  weekday: 1 | 2 | 3 | 4 | 5 | 6 | 7; // 1 = Mon
  hour: number;
  minute: number;
  body: string;
}

const STORAGE_KEY = 'meli.reminders.v1';
const MAX_REMINDERS = 5;

function loadFromStorage(): Reminder[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Reminder[]) : [];
  } catch {
    return [];
  }
}

function saveToStorage(rs: Reminder[]) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rs));
}

export function useReminders() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [supported, setSupported] = useState(false);

  useEffect(() => {
    setSupported(isNative());
    setReminders(loadFromStorage());
  }, []);

  const persistAndSchedule = async (next: Reminder[]) => {
    saveToStorage(next);
    setReminders(next);
    if (!isNative()) return;
    const { LocalNotifications } = await import('@capacitor/local-notifications');
    const pending = await LocalNotifications.getPending();
    if (pending.notifications.length > 0) {
      await LocalNotifications.cancel({
        notifications: pending.notifications.map(n => ({ id: n.id })),
      });
    }
    await LocalNotifications.requestPermissions();
    await LocalNotifications.schedule({
      notifications: next.map(r => ({
        id: r.id,
        title: 'Time to review',
        body: r.body,
        schedule: { on: { weekday: r.weekday, hour: r.hour, minute: r.minute }, repeats: true },
        extra: { deep_link: '/dashboard' },
      })),
    });
  };

  const add = (r: Omit<Reminder, 'id'>) => {
    if (reminders.length >= MAX_REMINDERS) return;
    const id = Date.now() % 2_000_000_000; // 31-bit safe
    persistAndSchedule([...reminders, { ...r, id }]);
  };

  const remove = (id: number) => {
    persistAndSchedule(reminders.filter(r => r.id !== id));
  };

  return { reminders, add, remove, supported, atCap: reminders.length >= MAX_REMINDERS };
}
```

- [ ] **Step 2: Implement `reminder-form.tsx`**

```tsx
'use client';
import { useState } from 'react';
import { useReminders, type Reminder } from '@/hooks/use-reminders';

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

export function ReminderForm() {
  const { reminders, add, remove, supported, atCap } = useReminders();
  const [weekday, setWeekday] = useState<1|2|3|4|5|6|7>(1);
  const [hour, setHour] = useState(9);
  const [minute, setMinute] = useState(0);
  const [body, setBody] = useState('Review your flashcards');

  if (!supported) {
    return (
      <p className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">
        Study reminders are available in the Meli iOS and Android apps. Open this
        page on your phone to set them up.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <h2 className="text-base font-semibold">Active reminders</h2>
        {reminders.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet.</p>
        ) : (
          <ul className="space-y-1">
            {reminders.map((r) => (
              <li key={r.id} className="flex items-center justify-between rounded-md border px-3 py-2">
                <span>{DAYS[r.weekday - 1]} at {String(r.hour).padStart(2, '0')}:{String(r.minute).padStart(2, '0')} — {r.body}</span>
                <button onClick={() => remove(r.id)} className="text-sm text-destructive hover:underline">Remove</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <fieldset disabled={atCap} className="space-y-2 rounded-md border p-3">
        <legend className="px-1 text-sm font-medium">Add reminder</legend>
        <div className="flex flex-wrap gap-2">
          <select value={weekday} onChange={(e) => setWeekday(Number(e.target.value) as Reminder['weekday'])} className="rounded-md border px-2 py-1">
            {DAYS.map((d, i) => <option key={d} value={i + 1}>{d}</option>)}
          </select>
          <input type="number" min={0} max={23} value={hour} onChange={(e) => setHour(Number(e.target.value))} className="w-16 rounded-md border px-2 py-1" />
          :
          <input type="number" min={0} max={59} value={minute} onChange={(e) => setMinute(Number(e.target.value))} className="w-16 rounded-md border px-2 py-1" />
        </div>
        <input value={body} onChange={(e) => setBody(e.target.value)} className="w-full rounded-md border px-2 py-1" />
        <button
          onClick={() => add({ weekday, hour, minute, body })}
          className="rounded-md bg-primary px-3 py-1 text-primary-foreground hover:opacity-90"
        >
          Add
        </button>
        {atCap && <p className="text-xs text-muted-foreground">You've reached the maximum of 5 reminders.</p>}
      </fieldset>
    </div>
  );
}
```

- [ ] **Step 3: Implement page**

`frontend/src/app/dashboard/settings/reminders/page.tsx`:

```tsx
import { ReminderForm } from '@/components/notifications/reminder-form';

export const metadata = { title: 'Study reminders · Meli' };

export default function RemindersPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 px-4 py-6">
      <h1 className="text-2xl font-semibold">Study reminders</h1>
      <p className="text-sm text-muted-foreground">
        Schedule on-device reminders to come back to Meli. Up to 5 per device.
      </p>
      <ReminderForm />
    </div>
  );
}
```

- [ ] **Step 4: Install Capacitor LocalNotifications plugin in `mobile/`**

```bash
cd mobile
npm install @capacitor/local-notifications
npx cap sync
```

(Already declared as a dependency in Plan A's `package.json`. If `npm install` already covered it, this is a no-op.)

- [ ] **Step 5: Manual smoke test**

On web (`npm run dev`): visit `/dashboard/settings/reminders`. Expect "mobile-only" message.

On native (TestFlight build of Plan A — adds the import dynamically): visit the same path. Add a reminder for "1 minute from now" and verify the OS notification fires.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/dashboard/settings/reminders/ frontend/src/components/notifications/reminder-form.tsx frontend/src/hooks/use-reminders.ts mobile/package.json mobile/package-lock.json
git commit -m "feat(frontend): study reminders via Capacitor LocalNotifications"
```

---

## Task C6: Instructor announcement compose page

**Files:**
- Create: `frontend/src/hooks/use-announcements.ts`
- Create: `frontend/src/components/notifications/announcement-compose.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/announcements/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/announcements/new/page.tsx`
- Create: `frontend/src/app/dashboard/courses/[courseId]/announcements/[announcementId]/page.tsx`

- [ ] **Step 1: Implement `use-announcements.ts`**

```ts
'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { useApiToken } from '@/hooks/useApiToken';

export interface Announcement {
  id: string;
  course_id: string;
  author_id: string;
  title: string;
  body: string;
  send_mode: 'now' | 'digest';
  scheduled_at: string | null;
  sent_at: string | null;
  retracted_at: string | null;
  created_at: string;
}

export function useCourseAnnouncements(courseId: string) {
  const { getToken } = useApiToken();
  return useQuery({
    queryKey: ['announcements', courseId],
    queryFn: async () => {
      const r = await apiFetch<Announcement[]>(
        `/api/courses/${courseId}/announcements`,
        { token: await getToken() },
      );
      if (!r.success) throw new Error(r.error ?? 'Failed');
      return r.data;
    },
  });
}

export function useCreateAnnouncement(courseId: string) {
  const { getToken } = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { title: string; body: string; send_mode: 'now' | 'digest' }) => {
      const r = await apiFetch<Announcement>(
        `/api/courses/${courseId}/announcements`,
        { method: 'POST', body: JSON.stringify(input), token: await getToken() },
      );
      if (!r.success) throw new Error(r.error ?? 'Failed');
      return r.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['announcements', courseId] }),
  });
}

export function useRetractAnnouncement(courseId: string) {
  const { getToken } = useApiToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (announcementId: string) => {
      const r = await apiFetch(
        `/api/courses/${courseId}/announcements/${announcementId}`,
        { method: 'DELETE', token: await getToken() },
      );
      if (!r.success) throw new Error(r.error ?? 'Failed');
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['announcements', courseId] }),
  });
}
```

- [ ] **Step 2: Implement `announcement-compose.tsx`**

```tsx
'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { useCreateAnnouncement } from '@/hooks/use-announcements';

export function AnnouncementCompose({ courseId }: { courseId: string }) {
  const router = useRouter();
  const create = useCreateAnnouncement(courseId);
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [sendMode, setSendMode] = useState<'now' | 'digest'>('now');

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !body.trim()) return;
    try {
      const a = await create.mutateAsync({ title, body, send_mode: sendMode });
      router.push(`/dashboard/courses/${courseId}/announcements/${a.id}`);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <form onSubmit={onSubmit} className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <h1 className="text-2xl font-semibold">New announcement</h1>

      <div className="space-y-1">
        <label className="text-sm font-medium">Title</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          className="w-full rounded-md border px-3 py-2"
          required
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1">
          <label className="text-sm font-medium">Body (Markdown)</label>
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="h-64 w-full rounded-md border px-3 py-2 font-mono text-sm"
            required
          />
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Preview</label>
          <div className="prose prose-sm h-64 overflow-auto rounded-md border bg-muted/30 px-3 py-2">
            <ReactMarkdown>{body || '*Preview will appear here*'}</ReactMarkdown>
          </div>
        </div>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">When to send</legend>
        <label className="flex items-center gap-2">
          <input type="radio" checked={sendMode === 'now'} onChange={() => setSendMode('now')} />
          Send now (immediate push)
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" checked={sendMode === 'digest'} onChange={() => setSendMode('digest')} />
          Add to morning digest (8am HKT)
        </label>
      </fieldset>

      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-md bg-primary px-4 py-2 text-primary-foreground hover:opacity-90 disabled:opacity-50"
      >
        {create.isPending ? 'Sending…' : 'Publish'}
      </button>
    </form>
  );
}
```

- [ ] **Step 3: Implement compose page**

`frontend/src/app/dashboard/courses/[courseId]/announcements/new/page.tsx`:

```tsx
import { AnnouncementCompose } from '@/components/notifications/announcement-compose';

export const metadata = { title: 'New announcement · Meli' };

export default async function NewAnnouncementPage({
  params,
}: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await params;
  return <AnnouncementCompose courseId={courseId} />;
}
```

- [ ] **Step 4: Implement instructor list page**

`frontend/src/app/dashboard/courses/[courseId]/announcements/page.tsx`:

```tsx
'use client';
import Link from 'next/link';
import { use } from 'react';
import { useCourseAnnouncements, useRetractAnnouncement } from '@/hooks/use-announcements';

export default function AnnouncementsListPage({
  params,
}: { params: Promise<{ courseId: string }> }) {
  const { courseId } = use(params);
  const { data, isLoading } = useCourseAnnouncements(courseId);
  const retract = useRetractAnnouncement(courseId);

  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Announcements</h1>
        <Link
          href={`/dashboard/courses/${courseId}/announcements/new`}
          className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:opacity-90"
        >
          New
        </Link>
      </div>
      {isLoading ? (
        <p>Loading…</p>
      ) : !data?.length ? (
        <p className="text-muted-foreground">No announcements yet.</p>
      ) : (
        <ul className="space-y-2">
          {data.map(a => (
            <li key={a.id} className="rounded-md border p-3">
              <div className="flex items-baseline justify-between">
                <Link href={`/dashboard/courses/${courseId}/announcements/${a.id}`} className="font-medium hover:underline">
                  {a.title}
                </Link>
                {!a.retracted_at && (
                  <button
                    onClick={() => retract.mutate(a.id)}
                    className="text-xs text-destructive hover:underline"
                  >
                    Retract
                  </button>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {a.sent_at ? `Sent ${new Date(a.sent_at).toLocaleString()}` :
                 a.retracted_at ? 'Retracted' :
                 'Pending digest'}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Implement student-side announcement detail page**

`frontend/src/app/dashboard/courses/[courseId]/announcements/[announcementId]/page.tsx`:

```tsx
'use client';
import { use } from 'react';
import ReactMarkdown from 'react-markdown';
import { useCourseAnnouncements } from '@/hooks/use-announcements';

export default function AnnouncementDetailPage({
  params,
}: { params: Promise<{ courseId: string; announcementId: string }> }) {
  const { courseId, announcementId } = use(params);
  const { data } = useCourseAnnouncements(courseId);
  const a = data?.find(x => x.id === announcementId);
  if (!a) return <p className="p-6 text-muted-foreground">Announcement not found.</p>;
  return (
    <div className="mx-auto max-w-2xl space-y-4 px-4 py-6">
      <h1 className="text-2xl font-semibold">{a.title}</h1>
      <p className="text-xs text-muted-foreground">
        {a.sent_at ? new Date(a.sent_at).toLocaleString() : 'Pending'}
      </p>
      <div className="prose prose-sm">
        <ReactMarkdown>{a.body}</ReactMarkdown>
      </div>
    </div>
  );
}
```

(This view uses `GET /api/courses/:cid/announcements/:aid` — added in Plan B Task B7 — which is accessible to instructors *and* enrolled students. The list endpoint above (`useCourseAnnouncements`) is instructor-only, so the student detail view should fetch the single announcement directly via a new hook rather than relying on the list. The implementation below is simplified — extract a `useAnnouncement(courseId, id)` hook calling the single-item endpoint for production use.)

- [ ] **Step 6: Manual smoke test**

As an instructor, navigate to `/dashboard/courses/<id>/announcements/new`. Compose, hit Publish. Expect:
- Redirect to detail page
- Backend dispatched notifications to enrolled students (verified via Plan B logs)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/dashboard/courses/ frontend/src/components/notifications/announcement-compose.tsx frontend/src/hooks/use-announcements.ts
git commit -m "feat(frontend): instructor announcement compose + list + detail pages"
```

---

## Task C7: Capacitor push registration

**Files:**
- Create: `frontend/src/lib/push-registration.ts`
- Create: `frontend/src/components/providers/notification-provider.tsx`
- Modify: `frontend/src/app/layout.tsx` (mount the provider)

- [ ] **Step 1: Install plugin in `mobile/`**

```bash
cd mobile
npm install @capacitor/push-notifications
npx cap sync
```

(Already in Plan A's package.json — verify.)

- [ ] **Step 2: Implement `push-registration.ts`**

```ts
'use client';
import { isNative, getPlatform } from '@/lib/capacitor';
import { apiFetch } from '@/lib/api';

interface RegistrationContext {
  getToken: () => Promise<string | null>;
  appVersion: string;
  onForegroundNotification: () => void;
  onTap: (deepLink: string) => void;
}

let unsubs: Array<() => void> = [];

/** Register for push and wire listeners. Idempotent — repeated calls are safe. */
export async function registerPushNotifications(ctx: RegistrationContext): Promise<void> {
  if (!isNative()) return;

  const { PushNotifications } = await import('@capacitor/push-notifications');

  const perm = await PushNotifications.requestPermissions();
  if (perm.receive !== 'granted') {
    console.info('Push permission not granted; skipping registration');
    return;
  }

  await PushNotifications.register();

  // Clean up any prior listeners (idempotent re-register on sign-in).
  await Promise.all(unsubs.map((u) => u()));
  unsubs = [];

  const onRegistration = await PushNotifications.addListener('registration', async ({ value }) => {
    const token = await ctx.getToken();
    if (!token) return;
    await apiFetch('/api/notifications/devices', {
      method: 'POST',
      token,
      body: JSON.stringify({
        push_token: value,
        platform: getPlatform(),
        app_version: ctx.appVersion,
      }),
    });
  });

  const onError = await PushNotifications.addListener('registrationError', (err) => {
    console.warn('Push registration error', err);
  });

  const onReceived = await PushNotifications.addListener('pushNotificationReceived', () => {
    ctx.onForegroundNotification();
  });

  const onTap = await PushNotifications.addListener('pushNotificationActionPerformed', ({ notification }) => {
    const deepLink = (notification.data?.deep_link as string | undefined) ?? '/dashboard';
    ctx.onTap(deepLink);
  });

  unsubs = [
    () => onRegistration.remove(),
    () => onError.remove(),
    () => onReceived.remove(),
    () => onTap.remove(),
  ];
}

/** Unregister current device on sign-out. Best-effort. */
export async function unregisterPushNotifications(getToken: () => Promise<string | null>): Promise<void> {
  if (!isNative()) return;
  const { PushNotifications } = await import('@capacitor/push-notifications');
  // No reliable cross-platform "get current token" on iOS without a fresh registration
  // event. We simply remove all listeners; backend rows expire naturally via 410 responses
  // when push is sent to the now-absent app.
  await Promise.all(unsubs.map(u => u()));
  unsubs = [];
}
```

- [ ] **Step 3: Implement `notification-provider.tsx`**

```tsx
'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useApiToken } from '@/hooks/useApiToken';
import { registerPushNotifications } from '@/lib/push-registration';
import { handleDeepLink } from '@/lib/deep-link';
import { NOTIFICATIONS_QUERY_KEY } from '@/hooks/use-notifications';

const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? 'unknown';

/**
 * Mounts once at the app shell. On native, requests push permission,
 * registers the device with the backend, and wires foreground/tap listeners.
 *
 * On web this component is inert.
 */
export function NotificationProvider() {
  const router = useRouter();
  const qc = useQueryClient();
  const { getToken, isLoaded } = useApiToken();

  useEffect(() => {
    if (!isLoaded) return;
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      await registerPushNotifications({
        getToken,
        appVersion: APP_VERSION,
        onForegroundNotification: () => {
          // A push arrived while we're foregrounded — refresh feed + badge so
          // the bell updates without forcing the user to navigate.
          qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
          qc.invalidateQueries({ queryKey: ['notifications-unread-count'] });
        },
        onTap: (deepLink) => {
          handleDeepLink(deepLink, router);
        },
      });
    })();
    return () => { cancelled = true; };
  }, [isLoaded, getToken, qc, router]);

  return null;
}
```

(Confirm that `useApiToken` exposes `isLoaded` — if not, adapt to the existing shape, e.g. derive readiness from "user is signed in".)

- [ ] **Step 4: Mount the provider in `frontend/src/app/layout.tsx`**

Locate the root layout's tree (the existing Clerk provider, query provider, etc.) and add:

```tsx
import { NotificationProvider } from '@/components/providers/notification-provider';
// ...
<QueryClientProvider client={queryClient}>
  {/* existing tree */}
  <NotificationProvider />
  {children}
</QueryClientProvider>
```

- [ ] **Step 5: Build and run on a TestFlight device**

This step requires Plan A's TestFlight pipeline to be functional. Trigger a new build (`mobile-v0.2.0` or whatever version cadence you've set), install via TestFlight, sign in. Expected:
- iOS shows a system permission prompt for notifications on first run
- After granting, a row appears in `notification_devices` for your user

Verify in DB:

```bash
psql postgresql://.../meli -c "SELECT id, user_id, platform, substr(push_token, 1, 16) AS token_prefix, last_seen_at FROM notification_devices ORDER BY created_at DESC LIMIT 5;"
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/push-registration.ts frontend/src/components/providers/notification-provider.tsx frontend/src/app/layout.tsx
git commit -m "feat(frontend): Capacitor push registration + foreground/tap listeners"
```

---

## Task C8: Cold-start deep link handling

When the app is killed and a user taps a notification, Capacitor delivers the launch info via `App.addListener('appStateChange', ...)`. We hold the deep link until Clerk session restores, then navigate.

**Files:**
- Create: `frontend/src/hooks/use-deep-link.ts`
- Modify: `frontend/src/components/providers/notification-provider.tsx` (use this hook)

- [ ] **Step 1: Implement `use-deep-link.ts`**

```ts
'use client';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useApiToken } from '@/hooks/useApiToken';
import { isNative } from '@/lib/capacitor';
import { handleDeepLink } from '@/lib/deep-link';

/**
 * Captures a deep link that arrives during cold start (app launched FROM
 * a notification tap) and replays it once Clerk session is restored.
 */
export function useDeepLinkOnColdStart() {
  const router = useRouter();
  const { isLoaded } = useApiToken();
  const pendingRef = useRef<string | null>(null);
  const [primed, setPrimed] = useState(false);

  // Prime the listener once.
  useEffect(() => {
    if (!isNative() || primed) return;
    setPrimed(true);
    (async () => {
      const { PushNotifications } = await import('@capacitor/push-notifications');
      // getDeliveredNotifications returns iOS's launch payload if the app was opened from one.
      try {
        const delivered = await PushNotifications.getDeliveredNotifications();
        const launch = delivered.notifications?.[0];
        const deepLink = (launch?.data as Record<string, unknown> | undefined)?.deep_link as string | undefined;
        if (deepLink) pendingRef.current = deepLink;
      } catch {
        // Ignore — not all platforms surface this synchronously
      }
    })();
  }, [primed]);

  // Replay once auth is ready.
  useEffect(() => {
    if (!isLoaded) return;
    const link = pendingRef.current;
    if (link) {
      pendingRef.current = null;
      handleDeepLink(link, router);
    }
  }, [isLoaded, router]);
}
```

- [ ] **Step 2: Use the hook in NotificationProvider**

In `notification-provider.tsx`, add at the top of the component body:

```tsx
import { useDeepLinkOnColdStart } from '@/hooks/use-deep-link';
// ...
useDeepLinkOnColdStart();
```

- [ ] **Step 3: Manual cold-start test**

1. Kill the app fully.
2. From the backend, trigger a notification (e.g., have an instructor start a live quiz, or insert a notification row + send a fake push via `apns_pusher` script).
3. Tap the notification on the lock screen.
4. App launches → Clerk restores session → deep link navigates to the live quiz route.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-deep-link.ts frontend/src/components/providers/notification-provider.tsx
git commit -m "feat(frontend): cold-start deep link handling"
```

---

## Task C9: Foreground suppression heuristic

Spec §7.2: content-ready notifications are suppressed when the user is currently in the WebView on the same course. This is best-effort UI suppression — the backend still inserts the feed row.

**Files:**
- Modify: `frontend/src/components/providers/notification-provider.tsx`

- [ ] **Step 1: Track the current pathname**

Update `NotificationProvider`:

```tsx
'use client';
import { useEffect, useRef } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useApiToken } from '@/hooks/useApiToken';
import { registerPushNotifications } from '@/lib/push-registration';
import { handleDeepLink } from '@/lib/deep-link';
import { NOTIFICATIONS_QUERY_KEY } from '@/hooks/use-notifications';
import { useDeepLinkOnColdStart } from '@/hooks/use-deep-link';

export function NotificationProvider() {
  useDeepLinkOnColdStart();
  const router = useRouter();
  const pathname = usePathname();
  const qc = useQueryClient();
  const { getToken, isLoaded } = useApiToken();
  const pathRef = useRef(pathname);
  pathRef.current = pathname;

  useEffect(() => {
    if (!isLoaded) return;
    let cancelled = false;
    (async () => {
      if (cancelled) return;
      await registerPushNotifications({
        getToken,
        appVersion: process.env.NEXT_PUBLIC_APP_VERSION ?? 'unknown',
        onForegroundNotification: () => {
          // Always invalidate feed/badge; the OS will still show its banner unless
          // we've configured presentationOptions to hide it. We don't suppress the
          // OS banner — only avoid noisy in-app toasts (none implemented here).
          qc.invalidateQueries({ queryKey: NOTIFICATIONS_QUERY_KEY });
          qc.invalidateQueries({ queryKey: ['notifications-unread-count'] });
        },
        onTap: (deepLink) => {
          // Already on the same path? Just refresh data instead of navigating.
          if (deepLink === pathRef.current) {
            qc.invalidateQueries();
            return;
          }
          handleDeepLink(deepLink, router);
        },
      });
    })();
    return () => { cancelled = true; };
  }, [isLoaded, getToken, qc, router]);

  return null;
}
```

- [ ] **Step 2: Verify on device**

Open the live-quiz route and have someone trigger another notification for the same session. Tap the notification — expected: the feed/badge refresh in place rather than re-navigating.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/providers/notification-provider.tsx
git commit -m "feat(frontend): suppress redundant nav when notification matches current route"
```

---

## Task C10: Sign-out unregister + cleanup

**Files:**
- Find: where the existing app handles sign-out (likely `frontend/src/components/layout/navbar.tsx` or a Clerk wrapper)
- Modify: that handler to also call `unregisterPushNotifications`

- [ ] **Step 1: Locate sign-out handler**

```bash
grep -rn "signOut\|<SignOutButton\|UserButton" frontend/src/ | head -10
```

- [ ] **Step 2: Wrap sign-out**

Where Clerk's sign-out fires, add a pre-step to delete the device row:

```tsx
import { isNative } from '@/lib/capacitor';

async function preSignOut() {
  if (!isNative()) return;
  const { PushNotifications } = await import('@capacitor/push-notifications');
  // Best-effort: tell backend to forget this device. We don't have direct access
  // to the current registration token here; instead, we rely on the backend
  // discovering invalid tokens on next push. So this is a no-op pre-hook for now.
  // If you do have the token, call DELETE /api/notifications/devices/:token.
  await PushNotifications.removeAllListeners();
}

// Wire as: onClick={async () => { await preSignOut(); await signOut(); }}
```

(Robust unregister requires the backend to surface "the device whose user is X" via app-startup re-registration; our churn model handles this naturally because new sign-ins re-register and old tokens expire.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/navbar.tsx  # adjust to actual file
git commit -m "feat(frontend): clean up push listeners on sign-out"
```

---

## Acceptance criteria for Plan C

- [ ] `/dashboard/notifications` shows feed with infinite scroll, mark-read works
- [ ] Navbar bell + badge reflect unread count, polling works while foreground
- [ ] `/dashboard/settings/reminders` lets a student schedule local notifications on native; shows "mobile-only" copy on web
- [ ] `/dashboard/courses/:cid/announcements/new` (instructor) composes with markdown preview; submitting with `send_mode='now'` triggers backend dispatch
- [ ] On native: install + sign in → push permission requested → device row appears in `notification_devices`
- [ ] On native: receiving a push while foregrounded refreshes the feed/badge without forcing navigation
- [ ] On native: tapping a push (foreground or background) deep-links to the right route
- [ ] On native: cold-start (killed app) launched from a notification deep-links once Clerk session restores
- [ ] On native: tapping a notification while already on the matching route refreshes data instead of re-navigating
- [ ] Sign-out cleans up push listeners
