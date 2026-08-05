/**
 * The safe failure contract from the approved handoff.
 *
 *   01  User copy names the affected object, consequence, preserved work, and
 *       safe next action.
 *   02  Raw exception, provider operation, object key, stack name, and request
 *       identifier stay in structured server logs.
 *   03  Recoverable errors keep the route, accepted files, schedule, outcomes,
 *       checkpoints, and review decisions intact.
 *
 * Plate 05 annotation 3 is the failure this module exists to make impossible:
 * the live product rendered `AttributeError: 'Settings' object has no attribute
 * 'llm_primary_model'` directly to an instructor.
 *
 * The backend is the first line of defence (it now emits typed codes, see
 * `app/services/failures.py`). This module is the second: even if an untyped or
 * legacy message reaches the client, `toSafeError` refuses to render anything
 * that pattern-matches as internals.
 */

import { ApiError } from "@/lib/api";
import { isUserSafeText } from "./user-safe-text";

/**
 * Typed failure codes shared with the backend `SourceFailureCode` enum. Adding
 * a code here without adding it to `SAFE_COPY` is a type error, so a new
 * backend failure mode cannot ship without user-safe copy.
 */
export type SafeErrorCode =
  | "unreadable_file"
  | "unsupported_format"
  | "file_too_large"
  | "empty_document"
  | "storage_unavailable"
  | "file_missing"
  | "analysis_unavailable"
  | "provider_unavailable"
  | "timeout"
  | "permission_denied"
  | "not_found"
  | "rate_limited"
  | "network"
  | "unknown";

/**
 * A failure rendered to a user. Every field maps to one clause the handoff
 * requires: what broke, what it means, what survived, and what to do next.
 */
export interface SafeError {
  readonly code: SafeErrorCode;
  /** What broke, naming the affected object when the caller supplies one. */
  readonly title: string;
  /** Consequence, in plain language. */
  readonly consequence: string;
  /** What was preserved. Rule 03: recoverable failures never lose work. */
  readonly preserved: string;
  /** The safe next action, as a sentence (the button label is separate). */
  readonly nextAction: string;
  /** Whether a Retry affordance should be offered. */
  readonly retryable: boolean;
  /**
   * `recoverable` keeps the route and accepted work; `blocking` needs the
   * object replaced or removed before the flow can continue.
   */
  readonly severity: "recoverable" | "blocking";
}

interface SafeCopy {
  readonly title: (object: string | null) => string;
  readonly consequence: string;
  readonly preserved: string;
  readonly nextAction: string;
  readonly retryable: boolean;
  readonly severity: "recoverable" | "blocking";
}

/**
 * The only place user-facing failure text is written. Copy names the object
 * where one is known ("Meli could not finish reading Week 1 reading.pdf")
 * and falls back to a neutral noun otherwise.
 */
const SAFE_COPY: Record<SafeErrorCode, SafeCopy> = {
  unreadable_file: {
    title: (object) =>
      object
        ? `Meli could not finish reading ${object}`
        : "Meli could not finish reading this file",
    consequence: "This source is not contributing to your course content yet.",
    preserved: "Your files are saved. Everything else you have set up is intact.",
    nextAction: "Retry now, or replace the file later.",
    retryable: true,
    severity: "recoverable",
  },
  unsupported_format: {
    title: (object) =>
      object ? `${object} is not a supported file type` : "Unsupported file type",
    consequence: "Meli cannot read this format, so it will not be used as a source.",
    preserved: "Your other sources and setup progress are saved.",
    nextAction: "Replace it with a PDF, DOCX, or PPTX file.",
    retryable: false,
    severity: "blocking",
  },
  file_too_large: {
    title: (object) => (object ? `${object} is too large` : "File is too large"),
    consequence: "Meli stopped before reading it, so it has not been added.",
    preserved: "Your other sources and setup progress are saved.",
    nextAction: "Split the file or upload a smaller version.",
    retryable: false,
    severity: "blocking",
  },
  empty_document: {
    title: (object) =>
      object ? `Meli found no readable text in ${object}` : "No readable text found",
    consequence:
      "Scanned pages and images without text cannot be used to generate course content.",
    preserved: "The file is still attached and your other work is saved.",
    nextAction: "Replace it with a text-based version.",
    retryable: false,
    severity: "blocking",
  },
  storage_unavailable: {
    title: (object) =>
      object ? `Meli could not open ${object}` : "Meli could not open this file",
    consequence: "The file could not be retrieved for processing just now.",
    preserved: "Nothing was lost. Your upload and setup progress are saved.",
    nextAction: "Retry in a moment.",
    retryable: true,
    severity: "recoverable",
  },
  file_missing: {
    title: (object) =>
      object ? `${object} is no longer stored` : "This file is no longer stored",
    // Separate from `storage_unavailable` so the copy can be honest: the
    // object is gone, so "Retry in a moment" would loop forever. Blocking and
    // non-retryable, with the one action that actually works.
    consequence: "Meli cannot read it, so it is not contributing to your course content.",
    preserved: "Everything else you have set up is intact.",
    nextAction: "Upload the file again.",
    retryable: false,
    severity: "blocking",
  },
  analysis_unavailable: {
    title: (object) =>
      object ? `Meli could not analyse ${object}` : "Meli could not finish the analysis",
    consequence: "Suggested outcomes and checkpoints are not ready yet.",
    preserved: "Your files and every completed step are saved.",
    // No Retry. This is the bucket for our own defects and misconfiguration
    // (a bad setting, a rejected provider key), so mirrors the backend's
    // RETRYABLE_CODES, which excludes it for the same reason: a retry re-runs
    // download, parse and embedding only to fail identically, at real cost.
    // Recovery is an operator fix, so the honest next action is to carry on.
    nextAction: "Continue setting up. Contact CLE support if this persists.",
    retryable: false,
    severity: "recoverable",
  },
  provider_unavailable: {
    title: (object) =>
      object ? `Meli could not analyse ${object} yet` : "Meli could not analyse this yet",
    // Deliberately separate from `analysis_unavailable`: same step, but the
    // cause is the model provider being busy or unreachable rather than our
    // configuration, so the same file genuinely can succeed on a second try
    // and Retry is an honest offer here.
    consequence: "The service Meli uses for analysis is busy right now.",
    preserved: "Your files and every completed step are saved.",
    nextAction: "Retry in a few minutes.",
    retryable: true,
    severity: "recoverable",
  },
  timeout: {
    title: (object) =>
      object ? `${object} took too long to process` : "This took too long to process",
    consequence: "Processing stopped before it finished.",
    preserved: "Your files and completed steps are saved.",
    nextAction: "Retry now.",
    retryable: true,
    severity: "recoverable",
  },
  permission_denied: {
    title: () => "You do not have access to this",
    consequence: "This action is limited to the people who own this course.",
    preserved: "Nothing was changed.",
    nextAction: "Ask the course owner for access.",
    retryable: false,
    severity: "blocking",
  },
  not_found: {
    title: (object) => (object ? `${object} was not found` : "This was not found"),
    consequence: "It may have been moved or removed.",
    preserved: "Nothing else was changed.",
    nextAction: "Go back and refresh the list.",
    retryable: false,
    severity: "blocking",
  },
  rate_limited: {
    title: () => "Too many requests for now",
    consequence: "Meli paused this action to stay within the usage limit.",
    preserved: "Your work is saved.",
    nextAction: "Try again in a few minutes.",
    retryable: true,
    severity: "recoverable",
  },
  network: {
    title: () => "Meli could not reach the server",
    consequence: "This action did not complete.",
    preserved: "Your work is saved on this device.",
    nextAction: "Check your connection and retry.",
    retryable: true,
    severity: "recoverable",
  },
  unknown: {
    title: (object) =>
      object ? `Something went wrong with ${object}` : "Something went wrong",
    consequence: "This action did not complete.",
    preserved: "Your saved work is intact.",
    nextAction: "Retry now. If it keeps happening, contact CLE support.",
    retryable: true,
    severity: "recoverable",
  },
};

/**
 * Re-exported so callers of this module get the predicate without reaching for
 * a second import. The implementation lives in `user-safe-text.ts` because
 * `lib/api.ts` needs it too and importing it from here would cycle.
 */
export { isUserSafeText } from "./user-safe-text";

function isSafeErrorCode(value: string): value is SafeErrorCode {
  return value in SAFE_COPY;
}

/**
 * Map an HTTP status onto a code when the backend did not supply a typed one.
 */
function codeFromStatus(status: number): SafeErrorCode {
  if (status === 401 || status === 403) return "permission_denied";
  if (status === 404) return "not_found";
  if (status === 413) return "file_too_large";
  if (status === 415) return "unsupported_format";
  if (status === 429) return "rate_limited";
  if (status === 408 || status === 504) return "timeout";
  return "unknown";
}

export interface ToSafeErrorOptions {
  /**
   * The user-visible name of the thing that failed: a filename, a course
   * name, a session title. Supplying it is what satisfies "names the affected
   * object"; it is never derived from an internal identifier.
   */
  readonly objectName?: string | null;
  /** Code to use when the error carries none. */
  readonly fallbackCode?: SafeErrorCode;
}

/**
 * Convert any thrown value into user-safe copy.
 *
 * Resolution order: an explicit typed `code` from the backend, then the HTTP
 * status, then the caller's fallback. The backend `message` is used only to
 * override the title, and only when it passes `isUserSafeText`, which is what
 * stops an `AttributeError` string from ever reaching the screen.
 */
export function toSafeError(
  error: unknown,
  options: ToSafeErrorOptions = {}
): SafeError {
  const objectName = options.objectName?.trim() || null;

  let code: SafeErrorCode = options.fallbackCode ?? "unknown";
  let backendMessage: string | undefined;

  if (error instanceof ApiError) {
    if (error.code && isSafeErrorCode(error.code)) {
      code = error.code;
    } else {
      code = codeFromStatus(error.status);
    }
    backendMessage = error.detail;
  } else if (
    error instanceof TypeError &&
    /fetch|network|load failed/i.test(error.message)
  ) {
    code = "network";
  }

  const copy = SAFE_COPY[code];
  const title =
    backendMessage && isUserSafeText(backendMessage)
      ? backendMessage
      : copy.title(objectName);

  return {
    code,
    title,
    consequence: copy.consequence,
    preserved: copy.preserved,
    nextAction: copy.nextAction,
    retryable: copy.retryable,
    severity: copy.severity,
  };
}

/**
 * Build a `SafeError` from a code the caller already knows (e.g. a source row
 * whose stored status is `failed` with a typed `error_code`). Used by the
 * setup Sources stage, which reads per-source state rather than catching a
 * thrown request.
 */
export function safeErrorFromCode(
  code: string | null | undefined,
  options: ToSafeErrorOptions = {}
): SafeError {
  const resolved: SafeErrorCode =
    code && isSafeErrorCode(code) ? code : options.fallbackCode ?? "unknown";
  const copy = SAFE_COPY[resolved];
  const objectName = options.objectName?.trim() || null;
  return {
    code: resolved,
    title: copy.title(objectName),
    consequence: copy.consequence,
    preserved: copy.preserved,
    nextAction: copy.nextAction,
    retryable: copy.retryable,
    severity: copy.severity,
  };
}

/**
 * One-line summary for compact surfaces (a toast, a list row) that cannot show
 * all four clauses. Always title + next action, never the raw message.
 */
export function safeErrorSummary(error: SafeError): string {
  return `${error.title}. ${error.nextAction}`;
}
