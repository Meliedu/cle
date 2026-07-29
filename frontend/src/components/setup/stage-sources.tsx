"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";

import { Skeleton } from "@/components/ui/skeleton";
import { StepSyllabus } from "@/components/setup/step-syllabus";
import { StepMaterials } from "@/components/setup/step-materials";
import { StepAnalyzer } from "@/components/setup/step-analyzer";
import {
  SourceStatusList,
  type SourceRow,
} from "@/components/setup/source-status-list";
import { useReprocessDocument } from "@/hooks/use-documents";

interface StageSourcesProps {
  readonly courseId: string;
  readonly sources: readonly SourceRow[];
  readonly isLoading: boolean;
  readonly onSaved: () => void;
  readonly onAdvance: () => void;
}

/**
 * Stage 2 of 5: Sources.
 *
 * Absorbs three backend steps (`syllabus`, `materials`, `analyzer_review`)
 * because to a user they are one job: give Meli the course material and let it
 * be read. Each remains a separate flag on the server, so publish gating and
 * per-step validation are unchanged.
 *
 * The source list sits at the top because it is the stage's actual state:
 * everything below it is the means of changing that state. When a source fails,
 * the recovery banner appears here with the file named and typed, user-safe
 * copy (Plate 05, rule 3), and every accepted file stays in place.
 */
export function StageSources({
  courseId,
  sources,
  isLoading,
  onSaved,
  onAdvance,
}: StageSourcesProps) {
  const t = useTranslations("teacher.setup");
  const reprocess = useReprocessDocument(courseId);
  const [replacing, setReplacing] = useState<string | null>(null);

  const handleRetry = useCallback(
    (source: SourceRow) => {
      // Retry re-runs processing for the SAME stored file. Nothing is deleted,
      // so an accepted upload is never lost to a failed parse.
      reprocess.mutate(source.id, { onSuccess: onSaved });
    },
    [reprocess, onSaved]
  );

  const handleReplace = useCallback((source: SourceRow) => {
    // Scrolls the upload affordance into view and marks which source is being
    // replaced; the existing file stays until the new one is accepted.
    setReplacing(source.id);
    document
      .getElementById("setup-materials")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <div className="space-y-10">
      <section aria-labelledby="setup-sources-state">
        <h2
          id="setup-sources-state"
          className="text-[18px] font-semibold tracking-tight text-[var(--color-text)]"
        >
          {t("sourcesTitle")}
        </h2>
        <p className="mt-1 text-[14px] text-[var(--color-text-secondary)]">
          {t("sourcesReason")}
        </p>

        <div className="mt-4">
          {isLoading ? (
            <Skeleton className="h-[120px] rounded-[var(--radius-xl)]" />
          ) : sources.length === 0 ? null : (
            <SourceStatusList
              sources={sources}
              onRetry={handleRetry}
              onReplace={handleReplace}
              isRetrying={reprocess.isPending}
            />
          )}
        </div>
      </section>

      <StepSyllabus courseId={courseId} onComplete={onSaved} />

      <div id="setup-materials" className="scroll-mt-24">
        <StepMaterials courseId={courseId} onComplete={onSaved} />
        {replacing ? (
          <p className="mt-2 text-[13px] text-[var(--color-text-muted)]">
            {t("replaceFile")}
          </p>
        ) : null}
      </div>

      <StepAnalyzer
        courseId={courseId}
        onComplete={() => {
          onSaved();
          onAdvance();
        }}
      />
    </div>
  );
}
