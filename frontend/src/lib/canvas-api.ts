import { apiFetch, type ApiEnvelope } from "@/lib/api";

// ---------- Types ----------

export interface CanvasConnection {
  readonly connected: boolean;
  readonly canvas_user_id?: number | null;
  readonly canvas_base_url?: string | null;
  readonly status?: string | null;
}

export interface CanvasOAuthStart {
  readonly authorize_url: string;
}

export interface CanvasCourseListing {
  readonly canvas_course_id: number;
  readonly name: string;
  readonly course_code: string | null;
  readonly term: string | null;
  readonly enrollment_type: string;
  readonly workflow_state: string;
  readonly already_linked_meli_course_id: string | null;
}

export interface CanvasLinkResult {
  readonly meli_course_id: string;
}

export interface CanvasJoinResult {
  readonly meli_course_id: string;
}

export interface CanvasFileRef {
  readonly canvas_file_id: number;
  readonly filename: string;
  readonly display_name: string | null;
  readonly size: number | null;
  readonly content_type: string | null;
  readonly updated_at: string | null;
}

export interface CanvasFileListing {
  readonly available: readonly CanvasFileRef[];
  readonly already_imported: readonly CanvasFileRef[];
}

export interface CanvasFileImportResult {
  readonly imported: number;
  readonly skipped: number;
  readonly errors: readonly {
    readonly canvas_file_id: number;
    readonly message: string;
  }[];
}

export interface CanvasRosterImportResult {
  readonly added: number;
  readonly unchanged: number;
  readonly dropped: number;
  readonly pending: number;
  readonly skipped_off_domain: number;
}

export interface CanvasSyncEvent {
  readonly id: string;
  readonly event_type: string;
  readonly status: string;
  readonly summary: string | null;
  readonly created_at: string;
}

// ---------- Fetch helpers ----------

function auth(token: string) {
  return { token } as const;
}

function unwrap<T>(envelope: ApiEnvelope<T>): T {
  return envelope.data;
}

// ---------- OAuth / connection ----------

export async function startCanvasOAuth(token: string): Promise<CanvasOAuthStart> {
  const env = await apiFetch<ApiEnvelope<CanvasOAuthStart>>(
    "/canvas/oauth/start",
    auth(token)
  );
  return unwrap(env);
}

export async function getCanvasConnection(
  token: string
): Promise<CanvasConnection> {
  const env = await apiFetch<ApiEnvelope<CanvasConnection>>(
    "/canvas/connection",
    auth(token)
  );
  return unwrap(env);
}

export async function disconnectCanvas(token: string): Promise<void> {
  await apiFetch<ApiEnvelope<unknown>>("/canvas/connection", {
    method: "DELETE",
    token,
  });
}

// ---------- Courses (teacher / student) ----------

export async function listCanvasCourses(
  token: string,
  role: "student" | "teacher"
): Promise<readonly CanvasCourseListing[]> {
  const env = await apiFetch<ApiEnvelope<readonly CanvasCourseListing[]>>(
    `/canvas/courses?role=${role}`,
    auth(token)
  );
  return unwrap(env);
}

export async function linkCanvasCourse(
  token: string,
  canvasCourseId: number
): Promise<CanvasLinkResult> {
  const env = await apiFetch<ApiEnvelope<CanvasLinkResult>>(
    `/canvas/courses/${canvasCourseId}/link`,
    { method: "POST", token }
  );
  return unwrap(env);
}

export async function joinCanvasCourse(
  token: string,
  canvasCourseId: number
): Promise<CanvasJoinResult> {
  const env = await apiFetch<ApiEnvelope<CanvasJoinResult>>(
    `/canvas/courses/${canvasCourseId}/join`,
    { method: "POST", token }
  );
  return unwrap(env);
}

// ---------- Course-level: files / roster / sync ----------

export async function listCanvasFiles(
  token: string,
  courseId: string
): Promise<CanvasFileListing> {
  const env = await apiFetch<ApiEnvelope<CanvasFileListing>>(
    `/courses/${courseId}/canvas/files`,
    auth(token)
  );
  return unwrap(env);
}

export async function importCanvasFiles(
  token: string,
  courseId: string,
  fileIds: readonly number[]
): Promise<CanvasFileImportResult> {
  const env = await apiFetch<ApiEnvelope<CanvasFileImportResult>>(
    `/courses/${courseId}/canvas/files/import`,
    {
      method: "POST",
      token,
      body: JSON.stringify({ file_ids: fileIds }),
    }
  );
  return unwrap(env);
}

export async function importCanvasRoster(
  token: string,
  courseId: string,
  sendInviteEmails: boolean
): Promise<CanvasRosterImportResult> {
  const env = await apiFetch<ApiEnvelope<CanvasRosterImportResult>>(
    `/courses/${courseId}/canvas/roster/import`,
    {
      method: "POST",
      token,
      body: JSON.stringify({ send_invite_emails: sendInviteEmails }),
    }
  );
  return unwrap(env);
}

export async function runCanvasSync(
  token: string,
  courseId: string
): Promise<void> {
  await apiFetch<ApiEnvelope<unknown>>(
    `/courses/${courseId}/canvas/sync`,
    { method: "POST", token }
  );
}

export async function listCanvasSyncEvents(
  token: string,
  courseId: string,
  limit = 20
): Promise<readonly CanvasSyncEvent[]> {
  const env = await apiFetch<ApiEnvelope<readonly CanvasSyncEvent[]>>(
    `/courses/${courseId}/canvas/sync-events?limit=${limit}`,
    auth(token)
  );
  return unwrap(env);
}
