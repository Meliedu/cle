"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { CheckCircle2, ClipboardList, Trophy } from "lucide-react";

import { PageHeader, StateBanner, EmptyState } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useMyScores,
  type ScoreArtifact,
  type ScoreCategoryRollup,
} from "@/hooks/use-scores";

interface StudentScoresProps {
  readonly courseId: string;
}

/**
 * S059 — the student's own score & participation record. Reads `useMyScores`
 * (enrollment-scoped; `null` when the student has no graded artifacts yet) and
 * lays out a per-category rollup with each category's weight + earned/possible
 * points and a per-artifact breakdown (earned vs possible, submitted or not).
 * Mobile-first single column. Loading / error / no-scores each render a
 * designed state — never a blank panel.
 */
export function StudentScores({ courseId }: StudentScoresProps) {
  const t = useTranslations("student.scores");
  const { data: record, isLoading, isError } = useMyScores(courseId);

  const backHref = `/student/courses/${courseId}/activities`;
  const header = (
    <PageHeader
      title={t("title")}
      description={t("description")}
      breadcrumb={
        <Link href={backHref} className="hover:text-[var(--color-text)]">
          {t("back")}
        </Link>
      }
    />
  );

  if (isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        {header}
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="h-20 w-full rounded-[var(--radius-xl)]" />
          <Skeleton className="h-32 w-full rounded-[var(--radius-xl)]" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        {header}
        <StateBanner
          tone="warning"
          title={t("error.title")}
          reason={t("error.reason")}
        />
      </div>
    );
  }

  const categories = record?.categories ?? [];
  if (!record || categories.length === 0) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        {header}
        <EmptyState
          icon={Trophy}
          title={t("empty.title")}
          reason={t("empty.reason")}
        />
      </div>
    );
  }

  const totalEarned = sum(categories.map((c) => c.earned_points));
  const totalPossible = sum(categories.map((c) => c.possible_points));

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      {header}

      <section
        aria-label={t("overall.label")}
        className="flex items-center justify-between gap-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4"
      >
        <div className="flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-full bg-[var(--color-primary-light)] text-[var(--color-primary)]">
            <Trophy aria-hidden="true" className="size-5" />
          </span>
          <div>
            <p className="text-[12px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("overall.label")}
            </p>
            <p className="text-[13px] text-[var(--color-text-secondary)]">
              {t("overall.caption")}
            </p>
          </div>
        </div>
        <p className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("points", {
            earned: fmt(totalEarned),
            possible: fmt(totalPossible),
          })}
        </p>
      </section>

      <div className="space-y-4">
        {categories.map((category) => (
          <CategoryCard key={category.category_id} category={category} />
        ))}
      </div>
    </div>
  );
}

function CategoryCard({ category }: { readonly category: ScoreCategoryRollup }) {
  const t = useTranslations("student.scores");
  return (
    <section className="space-y-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {category.category_name}
          </h2>
          {category.weight !== null ? (
            <span className="text-[12px] font-medium text-[var(--color-text-muted)]">
              {t("weight", { weight: fmt(category.weight) })}
            </span>
          ) : null}
        </div>
        <span className="text-[13px] font-semibold text-[var(--color-text)]">
          {t("points", {
            earned: fmt(category.earned_points),
            possible: fmt(category.possible_points),
          })}
        </span>
      </header>

      {category.artifacts.length === 0 ? (
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("category.noArtifacts")}
        </p>
      ) : (
        <ul className="divide-y divide-[var(--color-border)]/70">
          {category.artifacts.map((artifact) => (
            <ArtifactRow
              key={`${artifact.kind}-${artifact.artifact_id}`}
              artifact={artifact}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ArtifactRow({ artifact }: { readonly artifact: ScoreArtifact }) {
  const t = useTranslations("student.scores");
  const tk = useTranslations("student.scores.kind");
  return (
    <li className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {tk(artifact.kind)}
          </span>
          <span
            className={cn(
              "inline-flex items-center gap-1 text-[11px] font-medium",
              artifact.submitted
                ? "text-[var(--color-success)]"
                : "text-[var(--color-text-muted)]"
            )}
          >
            {artifact.submitted ? (
              <CheckCircle2 aria-hidden="true" className="size-3.5" />
            ) : (
              <ClipboardList aria-hidden="true" className="size-3.5" />
            )}
            {artifact.submitted ? t("submitted") : t("notSubmitted")}
          </span>
        </div>
        <p className="truncate text-[14px] font-medium text-[var(--color-text)]">
          {artifact.title}
        </p>
      </div>

      <div className="shrink-0 text-right">
        <p className="text-[13px] font-semibold text-[var(--color-text)]">
          {t("points", {
            earned: fmt(artifact.earned_points),
            possible: fmt(artifact.points),
          })}
        </p>
        {artifact.score_pct !== null ? (
          <p className="text-[12px] text-[var(--color-text-muted)]">
            {t("scorePct", { pct: fmt(artifact.score_pct) })}
          </p>
        ) : null}
      </div>
    </li>
  );
}

/** Sum a list of nullable numbers, ignoring nulls. */
function sum(values: readonly (number | null)[]): number {
  return values.reduce<number>((acc, v) => acc + (v ?? 0), 0);
}

/** Format a nullable number for display (drops trailing zeros; `—` for null). */
function fmt(value: number | null): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}
