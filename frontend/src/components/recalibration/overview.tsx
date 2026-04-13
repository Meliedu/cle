"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TransitionMatrix } from "./transition-matrix";
import { ItemTable } from "./item-table";
import { useRecalibrationOverview } from "@/hooks/use-recalibration";
import { formatRelativeTime } from "@/lib/format";

interface ContentTypeSummaryCardProps {
  readonly contentType: string;
  readonly itemsScanned: number;
  readonly itemsRelabeled: number;
  readonly relabelPct: number;
  readonly lastRun: string | null;
}

function ContentTypeSummaryCard({
  contentType,
  itemsScanned,
  itemsRelabeled,
  relabelPct,
  lastRun,
}: ContentTypeSummaryCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="capitalize">{contentType}</CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="space-y-2">
          <div className="flex items-center justify-between">
            <dt className="text-xs text-[var(--color-text-muted)]">Items scanned</dt>
            <dd className="text-sm font-semibold text-[var(--color-text)]">{itemsScanned}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-xs text-[var(--color-text-muted)]">Items relabeled</dt>
            <dd className="text-sm font-semibold text-[var(--color-text)]">
              {itemsRelabeled}{" "}
              <span className="font-normal text-[var(--color-text-muted)]">
                ({Math.round(relabelPct)}%)
              </span>
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="text-xs text-[var(--color-text-muted)]">Last run</dt>
            <dd className="text-xs text-[var(--color-text-secondary)]">
              {lastRun ? formatRelativeTime(lastRun) : "Never"}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

interface RecalibrationOverviewProps {
  readonly courseId: string;
}

export function RecalibrationOverview({ courseId }: RecalibrationOverviewProps) {
  // `isPending` (TanStack Query v5) is true on first load AND when there is no
  // cached data yet. `isLoading` would be false on a refetch with stale data,
  // letting the empty-state branch render even while a refetch is in flight.
  const { data, isPending, error } = useRecalibrationOverview(courseId);

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center" role="alert">
          <p className="text-sm text-[var(--color-error)]">
            {error instanceof Error ? error.message : "Failed to load recalibration data."}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isPending) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Card key={`skeleton-card-${i}`}>
              <CardHeader>
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-1/2" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-32 w-full" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data || data.summaries.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
          <p className="text-base font-medium text-[var(--color-text-secondary)]">
            No recalibration data yet
          </p>
          <p className="max-w-xs text-sm text-[var(--color-text-muted)]">
            Recalibration runs automatically as students answer questions.
            Check back after students have completed some practice sessions.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      {/* Summary cards */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
          Summary
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.summaries.map((summary) => (
            <ContentTypeSummaryCard
              key={summary.content_type}
              contentType={summary.content_type}
              itemsScanned={summary.items_scanned}
              itemsRelabeled={summary.items_relabeled}
              relabelPct={summary.relabel_pct}
              lastRun={summary.last_run}
            />
          ))}
        </div>
      </section>

      {/* Transition matrices */}
      {Object.keys(data.transition_matrices).length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
            Difficulty Transition Matrices
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {Object.entries(data.transition_matrices).map(([contentType, matrix]) => (
              <Card key={contentType}>
                <CardHeader>
                  <CardTitle className="capitalize">{contentType}</CardTitle>
                </CardHeader>
                <CardContent>
                  <TransitionMatrix matrix={matrix} contentType={contentType} />
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* Item detail table */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-text-secondary)] uppercase tracking-wide">
          Pool Items
        </h2>
        <Card>
          <CardContent className="pt-4">
            <ItemTable courseId={courseId} />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
