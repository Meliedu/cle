"use client";

import { useCallback, useMemo, useState } from "react";
import { useUser } from "@/hooks/use-auth";

export interface TodoItem {
  readonly id: string;
  readonly text: string;
  readonly done: boolean;
  readonly createdAt: string;
  readonly dueDate?: string;
}

interface UseTodosReturn {
  readonly items: readonly TodoItem[];
  readonly add: (text: string, dueDate?: string) => void;
  readonly toggle: (id: string) => void;
  readonly remove: (id: string) => void;
  readonly setDueDate: (id: string, dueDate: string | undefined) => void;
}

function storageKey(userId: string | null | undefined): string {
  return `meli:todos:${userId ?? "anon"}`;
}

function loadItems(userId: string | null | undefined): TodoItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isTodoItem);
  } catch {
    return [];
  }
}

function isTodoItem(v: unknown): v is TodoItem {
  if (v == null || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    typeof o.text === "string" &&
    typeof o.done === "boolean" &&
    typeof o.createdAt === "string"
  );
}

function writeItems(userId: string | null | undefined, next: readonly TodoItem[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(userId), JSON.stringify(next));
  } catch {
    // Swallow quota errors; the in-memory state still reflects user intent.
  }
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/**
 * User-managed to-do list persisted in localStorage, namespaced per Clerk user.
 * The return shape mirrors what a backend-backed hook would look like so the
 * migration later is component-free.
 */
export function useTodos(): UseTodosReturn {
  const { user } = useUser();
  const userId = user?.id ?? null;
  const [items, setItems] = useState<readonly TodoItem[]>(() => loadItems(userId));

  // Rehydrate once the user id resolves (Clerk may load after first render).
  const currentKey = storageKey(userId);
  const [hydratedKey, setHydratedKey] = useState<string>(currentKey);
  if (hydratedKey !== currentKey) {
    setHydratedKey(currentKey);
    setItems(loadItems(userId));
  }

  const persist = useCallback(
    (next: readonly TodoItem[]) => {
      writeItems(userId, next);
      setItems(next);
    },
    [userId]
  );

  const add = useCallback(
    (text: string, dueDate?: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      const next: TodoItem = {
        id: newId(),
        text: trimmed,
        done: false,
        createdAt: new Date().toISOString(),
        dueDate,
      };
      persist([next, ...items]);
    },
    [items, persist]
  );

  const toggle = useCallback(
    (id: string) => {
      persist(
        items.map((it) => (it.id === id ? { ...it, done: !it.done } : it))
      );
    },
    [items, persist]
  );

  const remove = useCallback(
    (id: string) => {
      persist(items.filter((it) => it.id !== id));
    },
    [items, persist]
  );

  const setDueDate = useCallback(
    (id: string, dueDate: string | undefined) => {
      persist(
        items.map((it) => (it.id === id ? { ...it, dueDate } : it))
      );
    },
    [items, persist]
  );

  return useMemo(
    () => ({ items, add, toggle, remove, setDueDate }),
    [items, add, toggle, remove, setDueDate]
  );
}
