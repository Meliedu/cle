"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSyllabusImports, useTriggerSyllabusImport } from "@/hooks/use-syllabus";
import { formatRelativeTime } from "@/lib/format";
import type { SyllabusImport, SyllabusImportStatus } from "@/lib/curriculum-types";

interface Props {
  readonly courseId: string;
}

function statusBadge(status: SyllabusImportStatus) {
  const base =
    "inline-block rounded px-2 py-0.5 text-xs font-medium";

  switch (status) {
    case "pending":
      return (
        <span className={`${base} bg-stone-100 text-stone-600`}>Pending</span>
      );
    case "parsed":
      return (
        <span className={`${base} bg-blue-100 text-blue-700`}>Parsed</span>
      );
    case "applied":
      return (
        <span className={`${base} bg-emerald-100 text-emerald-700`}>Applied</span>
      );
    case "failed":
      return (
        <span className={`${base} bg-rose-100 text-rose-700`}>Failed</span>
      );
    case "superseded":
      return (
        <span className={`${base} bg-stone-100 text-stone-400`}>Superseded</span>
      );
  }
}

function ImportRow({
  imp,
  courseId,
}: {
  readonly imp: SyllabusImport;
  readonly courseId: string;
}) {
  const triggerImport = useTriggerSyllabusImport(courseId);

  return (
    <li className="flex flex-wrap items-start gap-3 py-3 first:pt-0 last:pb-0">
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          {statusBadge(imp.status)}
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatRelativeTime(imp.created_at)}
          </span>
        </div>

        {imp.status === "failed" && imp.error_message && (
          <p className="mt-1 text-xs text-rose-600 break-words">
            {imp.error_message}
          </p>
        )}

        {imp.status === "applied" && imp.applied_at && (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Applied {formatRelativeTime(imp.applied_at)}
          </p>
        )}

        {imp.status === "pending" && (
          <p className="mt-1 flex items-center gap-1 text-xs text-[var(--color-text-muted)]">
            <Loader2 className="size-3 animate-spin" />
            Parsing…
          </p>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {imp.status === "parsed" && (
          <Link
            href={`/dashboard/courses/${courseId}/syllabus/imports/${imp.id}`}
            className="text-sm font-medium text-[var(--color-primary)] hover:underline"
          >
            Review &amp; apply
          </Link>
        )}

        {imp.status === "failed" && imp.document_id && (
          <Button
            size="sm"
            variant="outline"
            disabled={triggerImport.isPending}
            onClick={() => triggerImport.mutate(imp.document_id!)}
          >
            Re-trigger
          </Button>
        )}
      </div>
    </li>
  );
}

export function SyllabusImportList({ courseId }: Props) {
  const { data: imports, isLoading } = useSyllabusImports(courseId);

  const sorted = [...(imports ?? [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Import history ({isLoading ? "…" : sorted.length})</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 rounded-[var(--radius-md)]" />
            ))}
          </div>
        ) : sorted.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">
            No imports yet. Upload a syllabus above to get started.
          </p>
        ) : (
          <ul className="divide-y divide-[var(--color-border)]">
            {sorted.map((imp) => (
              <ImportRow key={imp.id} imp={imp} courseId={courseId} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
