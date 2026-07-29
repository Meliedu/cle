"use client";

import { useCallback, useMemo } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

/**
 * Query-string-backed UI state.
 *
 * The handoff requires filter and view state to survive navigation:
 *
 *   Use query, term, and lifecycle URL state; preserve filters across course
 *   entry and back navigation.          (Plate 02, rule 1)
 *   filters and selected date persist in URL state.        (P1, Calendar)
 *
 * Local `useState` cannot do that: entering a course and pressing Back
 * remounts the page with the filters reset. Putting the state in the URL also
 * makes a filtered roster shareable and gives Back real meaning.
 *
 * Writes use `replace` with `scroll: false` so adjusting a filter does not push
 * a history entry per keystroke or yank the viewport to the top.
 */
export interface UrlState {
  /** Current value for `key`, or `fallback` when absent. */
  readonly get: (key: string, fallback?: string) => string;
  /** Set one key. Passing an empty string or the default removes it. */
  readonly set: (key: string, value: string | null) => void;
  /** Set several keys atomically (one navigation, not one per key). */
  readonly setMany: (values: Record<string, string | null>) => void;
  /** Drop every key this surface owns. */
  readonly clear: (keys: readonly string[]) => void;
  /** The current query string, for building links that preserve state. */
  readonly search: string;
}

export function useUrlState(): UrlState {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const search = searchParams.toString();

  /**
   * Apply a mutation to the CURRENT query string.
   *
   * The base is read from `window.location.search`, not from the `search`
   * memo. `router.replace` updates the History API synchronously, but the
   * `useSearchParams` value only refreshes on the next render, so two writes
   * issued before that render (two filters changed in one tick, or fast typing)
   * would both start from the same stale snapshot and the second would silently
   * drop the first. Reading location at commit time makes each write build on
   * the previous one.
   *
   * `search` stays in the dependency list so the callback identity still
   * changes when the query does, which keeps memoised consumers correct.
   */
  const commit = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const current =
        typeof window === "undefined" ? search : window.location.search;
      const params = new URLSearchParams(current);
      mutate(params);
      const next = params.toString();
      router.replace(next ? `${pathname}?${next}` : pathname, {
        scroll: false,
      });
    },
    [pathname, router, search]
  );

  const get = useCallback(
    (key: string, fallback = "") => searchParams.get(key) ?? fallback,
    [searchParams]
  );

  const set = useCallback(
    (key: string, value: string | null) => {
      commit((params) => {
        if (value === null || value === "") params.delete(key);
        else params.set(key, value);
      });
    },
    [commit]
  );

  const setMany = useCallback(
    (values: Record<string, string | null>) => {
      commit((params) => {
        for (const [key, value] of Object.entries(values)) {
          if (value === null || value === "") params.delete(key);
          else params.set(key, value);
        }
      });
    },
    [commit]
  );

  const clear = useCallback(
    (keys: readonly string[]) => {
      commit((params) => {
        for (const key of keys) params.delete(key);
      });
    },
    [commit]
  );

  return useMemo(
    () => ({ get, set, setMany, clear, search }),
    [get, set, setMany, clear, search]
  );
}
