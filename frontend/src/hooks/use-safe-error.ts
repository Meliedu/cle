"use client";

import { useCallback } from "react";
import { useTranslations } from "next-intl";

import {
  safeErrorFromCode,
  toSafeError,
  type SafeError,
  type ToSafeErrorOptions,
} from "@/lib/contracts/safe-error";

/**
 * Localised failure copy.
 *
 * `lib/contracts/safe-error.ts` owns the CONTRACT (which codes exist, what is
 * retryable, what severity each carries) and ships English as the fallback so
 * non-React callers still get safe text. It cannot localise, because the
 * translator only exists inside React.
 *
 * That gap was user-visible: every failure title, consequence, preserved-work
 * sentence and next action rendered in English for a zh-Hant instructor, on
 * the setup surface where failures are most likely. This hook resolves the
 * same contract through `messages/*.json` instead, keeping severity and
 * retryability from the single source of truth.
 */
export function useSafeError() {
  const t = useTranslations("safeError");

  const localise = useCallback(
    (base: SafeError, objectName: string | null): SafeError => {
      const code = base.code;
      // A code with no message entry falls back to the English contract copy
      // rather than rendering a raw key path.
      const key = (field: string) => `${code}.${field}`;
      try {
        return {
          ...base,
          title: objectName
            ? t(key("titleNamed"), { object: objectName })
            : t(key("title")),
          consequence: t(key("consequence")),
          preserved: t(key("preserved")),
          nextAction: t(key("nextAction")),
        };
      } catch {
        // No message entry for this code: keep the English contract copy
        // rather than rendering a raw key path at the user.
        return base;
      }
    },
    [t]
  );

  const fromCode = useCallback(
    (code: string | null | undefined, options: ToSafeErrorOptions = {}): SafeError =>
      localise(safeErrorFromCode(code, options), options.objectName ?? null),
    [localise]
  );

  const fromError = useCallback(
    (error: unknown, options: ToSafeErrorOptions = {}): SafeError =>
      localise(toSafeError(error, options), options.objectName ?? null),
    [localise]
  );

  return { fromCode, fromError };
}
