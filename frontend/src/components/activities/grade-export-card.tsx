"use client";

import { useTranslations } from "next-intl";
import { Download, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StateBanner } from "@/components/patterns";
import { useGradeExport } from "@/hooks/use-scores";

interface GradeExportCardProps {
  readonly courseId: string;
}

/**
 * T075 — audited grade export. Triggers `useGradeExport` (a `text/csv` download)
 * and shows a persistent "every export is audited" note, because each download
 * appends a `grade_exports` audit row server-side. Surfaces a warning banner on
 * failure.
 */
export function GradeExportCard({ courseId }: GradeExportCardProps) {
  const t = useTranslations("teacher.grades");
  const gradeExport = useGradeExport(courseId);

  return (
    <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="space-y-1">
        <h3 className="text-[14px] font-semibold text-[var(--color-text)]">
          {t("title")}
        </h3>
        <p className="text-[13px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("description")}
        </p>
      </div>

      {gradeExport.isError ? (
        <StateBanner
          tone="warning"
          title={t("export.error.title")}
          reason={t("export.error.reason")}
        />
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          onClick={() => gradeExport.mutate()}
          disabled={gradeExport.isPending}
        >
          <Download />
          {gradeExport.isPending ? t("export.exporting") : t("export.button")}
        </Button>
      </div>

      <div className="flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3 py-2.5">
        <ShieldCheck
          aria-hidden="true"
          className="mt-0.5 size-4 shrink-0 text-[var(--color-primary)]"
        />
        <p className="text-[12px] leading-relaxed text-[var(--color-text-secondary)]">
          {t("export.note")}
        </p>
      </div>
    </section>
  );
}
