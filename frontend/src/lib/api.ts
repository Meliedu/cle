import { isUserSafeText } from "@/lib/contracts/user-safe-text";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export interface ApiEnvelope<T> {
  readonly success: boolean;
  readonly data: T;
}

export interface PaginatedEnvelope<T> extends ApiEnvelope<readonly T[]> {
  readonly meta: {
    readonly total: number;
    readonly page: number;
    readonly limit: number;
    readonly pages: number;
  };
}

export class ApiError extends Error {
  readonly status: number;
  /**
   * The backend's own message, but ONLY when it passes `isUserSafeText`.
   *
   * Several components render `error.detail` directly to get a more specific
   * message than the status fallback. Sanitising here rather than at those call
   * sites means an unsafe backend string is simply absent instead of being one
   * forgotten guard away from the screen.
   */
  readonly detail: string | undefined;
  /**
   * Machine-readable error code lifted from the response body when present.
   * Backend gate/validation errors carry a typed `code` either in the standard
   * `{ error: { code, message } }` envelope or in FastAPI's raw
   * `{ detail: { code, message } }` HTTPException shape. Callers switch on this
   * to branch the UI (e.g. `SETUP_INCOMPLETE`, `SETUP_NOT_OPEN`).
   */
  readonly code: string | undefined;

  constructor(
    status: number,
    userMessage: string,
    detail?: string,
    code?: string
  ) {
    // NOTE: userMessage is trusted here because every in-repo caller passes
    // either statusMessage() output or its own literal copy. Running it
    // through isUserSafeText would false-positive on our own strings (e.g.
    // "Request failed (HTTP 400)."). Callers must not pass backend text;
    // apiFetch is the boundary that gates that on a typed code.
    super(userMessage);
    this.name = "ApiError";
    this.status = status;
    // Same allowlist rule as `message`: backend text is retained only when
    // the backend also typed it with a code. isUserSafeText remains as a
    // second filter, never as the only one.
    this.detail =
      detail && code && isUserSafeText(detail) ? detail : undefined;
    this.code = code;
  }
}

/**
 * Pull a `{ code?, message? }` pair out of an error response body, tolerating
 * both the app envelope (`{ error: { code, message } }`) and FastAPI's native
 * `{ detail: ... }` shape (object with `code`/`message`, or a bare string).
 */
function extractError(payload: unknown): {
  code?: string;
  message?: string;
} {
  if (!payload || typeof payload !== "object") return {};
  const body = payload as Record<string, unknown>;

  const envelope = body.error;
  if (envelope && typeof envelope === "object") {
    const e = envelope as Record<string, unknown>;
    return {
      code: typeof e.code === "string" ? e.code : undefined,
      message: typeof e.message === "string" ? e.message : undefined,
    };
  }

  const detail = body.detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as Record<string, unknown>;
    return {
      code: typeof d.code === "string" ? d.code : undefined,
      message: typeof d.message === "string" ? d.message : undefined,
    };
  }
  if (typeof detail === "string") return { message: detail };

  return {};
}

export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 401 || err.status === 403);
}

/**
 * Safe message for callers that cannot go through `apiFetch`.
 *
 * A few paths need the raw `fetch`/`XMLHttpRequest` object: upload progress
 * events, multipart bodies. They still parse an error body, so without this
 * they would read `error.message` or `detail` straight onto the screen and
 * bypass the boundary every other caller gets for free. Same rule as
 * `apiFetch`: the backend's text is used only when it also typed the failure
 * with a `code`, otherwise the caller's own fallback copy is shown.
 */
export function safeBackendMessage(payload: unknown, fallback: string): string {
  const { code, message } = extractError(payload);
  return message && code && isUserSafeText(message) ? message : fallback;
}

/**
 * Turn a status plus an optional backend message into copy safe to render.
 *
 * Roughly thirty components render `ApiError.message` directly, so this
 * boundary is the only place a guard reliably covers them all: a handler that
 * does `raise HTTPException(400, detail=str(exc))` would otherwise put an
 * exception on screen through every one of them. That is the class of defect
 * the release contract forbids ("Raw exception, provider operation, object key,
 * stack name, and request identifier stay in structured server logs").
 *
 * The gate is an ALLOWLIST, not a pattern denylist. A denylist fails OPEN: an
 * unrecognised string renders, so every backend failure shape nobody thought to
 * write a regex for reaches users. `KeyError 'course_id'`, `relation "documents"
 * does not exist`, and `Expecting value: line 1 column 1 (char 0)` all slip past
 * a reasonable pattern list. Instead, a backend message is surfaced only when
 * the response also carried a typed `code`, which is the backend asserting the
 * text is deliberate user copy rather than an exception that happened to escape.
 * `isUserSafeText` is kept as a second filter, so a typed-but-careless message
 * still cannot ship internals.
 */
function userFacingMessage(
  status: number,
  backendMessage: string | undefined,
  code: string | undefined
): string {
  const safeMessage =
    backendMessage && code && isUserSafeText(backendMessage)
      ? backendMessage
      : undefined;
  return statusMessage(status, safeMessage);
}

function statusMessage(
  status: number,
  backendMessage: string | undefined
): string {
  if (status === 401 || status === 403) {
    return "You are not authorized to perform this action.";
  }
  if (status === 404) {
    return "The requested resource was not found.";
  }
  if (status === 429) {
    return "Rate limit reached. Please try again in a moment.";
  }
  if (status >= 500) {
    return "Something went wrong on our side. Please try again shortly.";
  }
  if (status === 422 && backendMessage) {
    return backendMessage;
  }
  if (status >= 400 && status < 500 && backendMessage) {
    return backendMessage;
  }
  return `Request failed (HTTP ${status}).`;
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<T> {
  const { token, body, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string>),
  };

  // Only set JSON Content-Type when the caller hasn't provided a FormData
  // body. FormData needs the browser to set its own multipart boundary.
  const isFormData =
    typeof FormData !== "undefined" && body instanceof FormData;
  if (!isFormData && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...fetchOptions,
    body,
    headers,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const { code, message } = extractError(payload);
    throw new ApiError(
      response.status,
      userFacingMessage(response.status, message, code),
      message,
      code
    );
  }

  return response.json();
}
