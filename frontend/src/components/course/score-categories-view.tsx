"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowRight, SlidersHorizontal } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, StateBanner } from "@/components/patterns";
import { useScoreCategories, type ScoreCategory } from "@/hooks/use-setup";

interface ScoreCategoriesViewProps {
  readonly courseId: string;
}

type Translate = ReturnType<typeof useTranslations>;

/** A `null`/absent weight = ungraded practice; otherwise a percent toward the record. */
function weightLabel(t: Translate, weight: number | null): string {
  return weight === null || weight === undefined
    ? t("ungraded")
    : t("weightValue", { weight });
}

/**
 * T035 — read-only score-categories view. Surfaces the course's score
 * categories (`useScoreCategories`, shared with the P1 setup score-policy step)
 * as a teacher reference on the enrollment / overview page: name, weight toward
 * the course record (or "practice"), and points pool. Editing lives in the
 * setup score-policy step — this view only reads and links back there.
 */
export function ScoreCategoriesView({ courseId }: ScoreCategoriesViewProps) {
  const t = useTranslations("teacher.enrollment.scoreCategories");
  const { data, isLoading, isError } = useScoreCategories(courseId);
  const editHref = `/teacher/courses/${courseId}/setup?step=score_policy`;

  const categories: readonly ScoreCategory[] = data
    ? [...data].sort((a, b) => a.sort - b.sort)
    : [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
            {t("title")}
          </h2>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            {t("subtitle")}
          </p>
        </div>
        <Link
          href={editHref}
          className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[var(--color-primary)] hover:underline"
        >
          <SlidersHorizontal aria-hidden="true" className="size-3.5" />
          {t("edit")}
          <ArrowRight aria-hidden="true" className="size-3.5" />
        </Link>
      </div>

      {isError ? (
        <StateBanner
          tone="warning"
          title={t("error.title")}
          reason={t("error.reason")}
        />
      ) : isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-11 w-full rounded-[var(--radius-md)]" />
          ))}
        </div>
      ) : categories.length === 0 ? (
        <EmptyState title={t("empty.title")} reason={t("empty.reason")} />
      ) : (
        <div className="overflow-x-auto rounded-[var(--radius-xl)] border border-[var(--color-border)]">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[12px] uppercase tracking-wide text-[var(--color-text-muted)]">
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.category")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.weight")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.points")}
                </th>
                <th scope="col" className="px-4 py-2.5 font-medium">
                  {t("columns.status")}
                </th>
              </tr>
            </thead>
            <tbody>
              {categories.map((category) => {
                const graded =
                  category.weight !== null && category.weight !== undefined;
                return (
                  <tr
                    key={category.id}
                    className="border-b border-[var(--color-border)] last:border-b-0"
                  >
                    <td className="px-4 py-3 font-medium text-[var(--color-text)]">
                      {category.name}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-[var(--color-text-secondary)]">
                      {weightLabel(t, category.weight)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-[var(--color-text-secondary)]">
                      {category.points_pool ?? t("noPoints")}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={graded ? "secondary" : "outline"}>
                        {graded ? t("status.graded") : t("status.practice")}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
