"use client";

import { useState, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { useSyllabusImports, useApplySyllabusImport } from "@/hooks/use-syllabus";

interface Props {
  readonly courseId: string;
  readonly importId: string;
}

// --- helpers ----------------------------------------------------------------

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function safeParseJson(
  raw: string
): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return { ok: false, error: "Top-level value must be a JSON object" };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof SyntaxError ? err.message : "Invalid JSON",
    };
  }
}

function asArray(v: unknown): readonly unknown[] {
  return Array.isArray(v) ? (v as readonly unknown[]) : [];
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" ? v : fallback;
}

// --- preview panel ----------------------------------------------------------

interface Module {
  name?: unknown;
  order_index?: unknown;
}
interface Meeting {
  meeting_index?: unknown;
  title?: unknown;
  scheduled_at?: unknown;
  module_index?: unknown;
}
interface Objective {
  statement?: unknown;
  bloom_level?: unknown;
  scope?: unknown;
}
interface AssignmentItem {
  title?: unknown;
  kind?: unknown;
  due_at?: unknown;
  weight?: unknown;
}

function PayloadPreview({ payload }: { readonly payload: Record<string, unknown> }) {
  const modules = asArray(payload.modules) as Module[];
  const meetings = asArray(payload.meetings) as Meeting[];
  const objectives = asArray(payload.objectives) as Objective[];
  const assignments = asArray(payload.assignments) as AssignmentItem[];

  return (
    <div className="space-y-4 text-sm">
      <section>
        <h3 className="mb-1.5 font-semibold text-[var(--color-text)]">
          Modules ({modules.length})
        </h3>
        {modules.length === 0 ? (
          <p className="text-[var(--color-text-muted)]">None</p>
        ) : (
          <ul className="space-y-0.5 text-[var(--color-text-secondary)]">
            {modules.map((m, i) => (
              <li key={i} className="flex items-center gap-2">
                <span className="text-[var(--color-text-muted)]">
                  #{asNumber(m.order_index, i)}
                </span>
                {asString(m.name, "(unnamed)")}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1.5 font-semibold text-[var(--color-text)]">
          Meetings ({meetings.length})
        </h3>
        {meetings.length === 0 ? (
          <p className="text-[var(--color-text-muted)]">None</p>
        ) : (
          <ul className="space-y-0.5 text-[var(--color-text-secondary)]">
            {meetings.map((m, i) => {
              const scheduledAt = asString(m.scheduled_at);
              const dateStr = scheduledAt
                ? new Date(scheduledAt).toLocaleDateString()
                : "—";
              return (
                <li key={i}>
                  <span className="text-[var(--color-text-muted)]">
                    #{asNumber(m.meeting_index, i)}
                  </span>{" "}
                  {asString(m.title, "(no title)")} · {dateStr}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1.5 font-semibold text-[var(--color-text)]">
          Objectives ({objectives.length})
        </h3>
        {objectives.length === 0 ? (
          <p className="text-[var(--color-text-muted)]">None</p>
        ) : (
          <ul className="space-y-0.5 text-[var(--color-text-secondary)]">
            {objectives.map((o, i) => (
              <li key={i}>
                <span className="mr-1 rounded bg-[var(--color-primary-light)] px-1 py-0.5 text-xs text-[var(--color-primary)]">
                  {asString(o.bloom_level, "?")}
                </span>
                {truncate(asString(o.statement, "(empty)"), 80)}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1.5 font-semibold text-[var(--color-text)]">
          Assignments ({assignments.length})
        </h3>
        {assignments.length === 0 ? (
          <p className="text-[var(--color-text-muted)]">None</p>
        ) : (
          <ul className="space-y-0.5 text-[var(--color-text-secondary)]">
            {assignments.map((a, i) => {
              const dueAt = asString(a.due_at);
              const dateStr = dueAt
                ? new Date(dueAt).toLocaleDateString()
                : "—";
              const weight = asString(a.weight, "");
              return (
                <li key={i}>
                  {asString(a.title, "(untitled)")}
                  <span className="ml-1 text-[var(--color-text-muted)]">
                    · {asString(a.kind, "other")} · due {dateStr}
                    {weight ? ` · ${weight}` : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

// --- main component ---------------------------------------------------------

export function SyllabusPayloadReview({ courseId, importId }: Props) {
  const router = useRouter();
  const { data: imports, isLoading } = useSyllabusImports(courseId);
  const applyImport = useApplySyllabusImport(courseId);

  const imp = useMemo(
    () => (imports ?? []).find((i) => i.id === importId),
    [imports, importId]
  );

  const initialJson = useMemo(
    () =>
      imp?.parsed_payload
        ? JSON.stringify(imp.parsed_payload, null, 2)
        : "{}",
    [imp?.parsed_payload]
  );

  const [jsonText, setJsonText] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);

  const effectiveJson = jsonText ?? initialJson;
  const parseResult = useMemo(
    () => safeParseJson(effectiveJson),
    [effectiveJson]
  );

  const handleJsonChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setJsonText(e.target.value);
    },
    []
  );

  const handleApply = useCallback(async () => {
    if (!parseResult.ok || !imp) return;
    setApplyError(null);
    try {
      await applyImport.mutateAsync({
        importId: imp.id,
        payload: parseResult.value,
      });
      router.push(`/dashboard/courses/${courseId}/syllabus`);
    } catch (err) {
      setApplyError(
        err instanceof Error ? err.message : "Failed to apply import"
      );
    }
  }, [parseResult, imp, applyImport, courseId, router]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-96 rounded-[var(--radius-lg)]" />
      </div>
    );
  }

  if (!imp) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <AlertCircle className="size-8 text-[var(--color-text-muted)]" />
        <p className="text-sm text-[var(--color-text-muted)]">Import not found.</p>
      </div>
    );
  }

  const canApply = imp.status === "parsed" && parseResult.ok;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--color-text)]">
          Review syllabus import
        </h1>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          Edit the JSON payload if needed, then apply to create curriculum items.
        </p>
      </div>

      {imp.status !== "parsed" && (
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-warning)] bg-[var(--color-warning-light)] px-3 py-2 text-sm text-[var(--color-warning)]">
          <AlertCircle className="size-4 shrink-0" />
          This import has status &ldquo;{imp.status}&rdquo; and cannot be applied.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left: editable JSON */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Payload JSON</CardTitle>
          </CardHeader>
          <CardContent>
            <Textarea
              className="h-[500px] font-mono text-xs"
              value={effectiveJson}
              onChange={handleJsonChange}
              spellCheck={false}
            />
            {!parseResult.ok && (
              <p className="mt-2 text-xs text-[var(--color-error)]">
                JSON error: {parseResult.error}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Right: live preview */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Preview</CardTitle>
          </CardHeader>
          <CardContent>
            {parseResult.ok ? (
              <PayloadPreview payload={parseResult.value} />
            ) : (
              <p className="text-sm text-[var(--color-text-muted)]">
                Fix the JSON to see a preview.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {applyError && (
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-error)] bg-[var(--color-error-light)] px-3 py-2 text-sm text-[var(--color-error)]">
          <AlertCircle className="size-4 shrink-0" />
          {applyError}
        </div>
      )}

      <div className="flex justify-end gap-3">
        <Button
          variant="outline"
          onClick={() =>
            router.push(`/dashboard/courses/${courseId}/syllabus`)
          }
        >
          Cancel
        </Button>
        <Button
          disabled={!canApply || applyImport.isPending}
          onClick={handleApply}
        >
          {applyImport.isPending && (
            <Loader2 className="mr-2 size-4 animate-spin" />
          )}
          Apply to curriculum
        </Button>
      </div>
    </div>
  );
}
