const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

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
  readonly detail: string | undefined;

  constructor(status: number, userMessage: string, detail?: string) {
    super(userMessage);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isAuthError(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 401 || err.status === 403);
}

function userFacingMessage(
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
  const { token, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...fetchOptions,
    headers,
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string } }
      | null;
    const backendMessage = payload?.error?.message;
    throw new ApiError(
      response.status,
      userFacingMessage(response.status, backendMessage),
      backendMessage
    );
  }

  return response.json();
}
