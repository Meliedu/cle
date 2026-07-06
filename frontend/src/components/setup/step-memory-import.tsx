"use client";

import { useTranslations } from "next-intl";
import { Archive } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/patterns";

/**
 * Feature flag gate for the previous-term memory import (T023). The real import
 * ships in P7; in P1 the screen is an informational stub that is hidden unless
 * `NEXT_PUBLIC_MEMORY_IMPORT` is explicitly set to `enabled`. Accessed directly
 * (not destructured) so Next.js can statically inline it at build time.
 */
export function isMemoryImportEnabled(): boolean {
  return process.env.NEXT_PUBLIC_MEMORY_IMPORT === "enabled";
}

interface StepMemoryImportProps {
  /** Fired when the teacher dismisses the (optional, non-blocking) step. */
  readonly onSkip?: () => void;
}

/**
 * T023 — previous-term memory import (STUB). This step is NOT one of the backend
 * `SETUP_STEP_KEYS`, so it never gates publish; it is a purely informational
 * placeholder for the P7 feature. It renders nothing unless the
 * `NEXT_PUBLIC_MEMORY_IMPORT` flag is `enabled`, and even then only explains
 * that reusing a prior term's evidence pack is coming later — no data is moved.
 */
export function StepMemoryImport({ onSkip }: StepMemoryImportProps) {
  const t = useTranslations("teacher.setup.memoryImport");

  if (!isMemoryImportEnabled()) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2.5">
        <h2 className="text-[15px] font-semibold tracking-tight text-[var(--color-text)]">
          {t("title")}
        </h2>
        <Badge variant="outline">{t("comingSoonBadge")}</Badge>
      </div>

      <div className="rounded-[var(--radius-xl)] border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]">
        <EmptyState
          variant="empty"
          icon={Archive}
          title={t("stub.title")}
          reason={t("stub.reason")}
          action={
            onSkip ? (
              <Button type="button" size="sm" variant="outline" onClick={onSkip}>
                {t("skip")}
              </Button>
            ) : undefined
          }
        />
      </div>
    </div>
  );
}
