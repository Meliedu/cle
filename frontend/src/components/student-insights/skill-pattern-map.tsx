"use client";

import { useTranslations } from "next-intl";
import { Layers } from "lucide-react";

import { StateBanner } from "@/components/patterns";
import { Skeleton } from "@/components/ui/skeleton";
import { useSkillMap } from "@/hooks/use-insights";

interface SkillPatternMapProps {
  readonly courseId: string;
}

/**
 * S065 — student skill pattern map. The pilot `skill_taxonomy` exists in config,
 * but NO concept→skill link exists in the schema (Decision 5), so the payload
 * carries `has_evidence=false` on every skill. This renders the config grid with
 * EVERY cell in the honest no-evidence state and one explicit reason — it never
 * fabricates a skill score it cannot back up. This is the designed forward-compat
 * seam for a future concept→skill mapping.
 */
export function SkillPatternMap({ courseId }: SkillPatternMapProps) {
  const t = useTranslations("student.insights.skills");
  const { data, isLoading, isError } = useSkillMap(courseId);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-20 rounded-[var(--radius-xl)]" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <StateBanner
        tone="warning"
        title={t("error.title")}
        reason={t("error.reason")}
      />
    );
  }

  return (
    <section className="space-y-3">
      <header className="space-y-1">
        <h2 className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          <Layers
            aria-hidden="true"
            className="size-4 text-[var(--color-text-muted)]"
          />
          {t("title")}
        </h2>
        <p className="text-[13px] text-[var(--color-text-secondary)]">
          {t("subtitle")}
        </p>
      </header>

      {/* Decision 5 — one honest reason for the whole grid's no-evidence state. */}
      <StateBanner tone="waiting" title={t("noEvidence")} reason={t("reason")} />

      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {data.skills.map((skill) => (
          <li
            key={skill.skill}
            data-skill={skill.skill}
            className="flex flex-col gap-1 rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3 py-3"
          >
            <span className="text-[13px] font-semibold text-[var(--color-text)]">
              {skill.label}
            </span>
            <span className="text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              {t("noEvidence")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
