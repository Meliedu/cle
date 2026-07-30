"use client";

import { useLocale, useTranslations } from "next-intl";

import { cn } from "@/lib/utils";
import type { SourceRollup } from "@/lib/contracts/state";
import type { SourceRow } from "@/components/setup/source-status-list";

interface SetupContextRailProps {
  readonly sources: readonly SourceRow[];
  readonly rollup: SourceRollup;
  /** Epoch ms of the last successful source-state read, or null if none yet. */
  readonly lastCheckedAt: number | null;
}

/**
 * The setup right rail: provenance and safe-to-leave state (Plate 05, rule 4).
 *
 *   provenance and safe-to-leave status stay visible
 *
 * Two jobs, both about trust:
 *
 *   1. Provenance answers "what is Meli actually using for this step?", so a
 *      derived outcome or checkpoint is traceable to a file without opening a
 *      separate admin tool (component contract, `ProvenanceAside`).
 *   2. Safe-to-leave answers "can I close this tab?". Processing continues
 *      server-side, and saying so is what makes the safe exit believable.
 */
export function SetupContextRail({
  sources,
  rollup,
  lastCheckedAt,
}: SetupContextRailProps) {
  const t = useTranslations("teacher.setup");
  const locale = useLocale();

  const overall: "ok" | "working" | "warning" =
    rollup.needsAttention > 0
      ? "warning"
      : rollup.inFlight > 0
        ? "working"
        : "ok";

  return (
    <aside className="space-y-8">
      <section aria-labelledby="setup-provenance">
        <h2
          id="setup-provenance"
          className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]"
        >
          {t("provenanceTitle")}
        </h2>
        <p className="mt-1 text-[13px] text-[var(--color-text-muted)]">
          {t("provenanceReason")}
        </p>

        {sources.length === 0 ? (
          <p className="mt-4 text-[13px] text-[var(--color-text-muted)]">
            {t("provenanceEmpty")}
          </p>
        ) : (
          <dl className="mt-4 space-y-2.5">
            {sources.map((source) => (
              <div
                key={source.id}
                className="flex items-baseline justify-between gap-3"
              >
                <dt className="min-w-0 truncate text-[13px] text-[var(--color-text-secondary)]">
                  {source.name}
                </dt>
                <dd
                  className={cn(
                    "shrink-0 text-[13px] font-medium",
                    source.readiness === "ready"
                      ? "text-[var(--color-success)]"
                      : source.readiness === "processing" ||
                          source.readiness === "uploading"
                        ? "text-[var(--color-primary-text)]"
                        : source.readiness === "idle"
                          ? "text-[var(--color-text-muted)]"
                          : "text-[var(--color-error)]"
                  )}
                >
                  {t(
                    source.readiness === "ready"
                      ? "grounded"
                      : source.readiness === "processing"
                        ? "processing"
                        : source.readiness === "uploading" ||
                            source.readiness === "idle"
                          ? "queued"
                          : "failed"
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section
        aria-labelledby="setup-safe-to-leave"
        className="border-t border-[var(--color-border)] pt-6"
      >
        <h2
          id="setup-safe-to-leave"
          className="text-[14px] font-semibold tracking-tight text-[var(--color-text)]"
        >
          {t("safeToLeaveTitle")}
        </h2>

        <ul className="mt-3 space-y-1 text-[13px] text-[var(--color-text-secondary)]">
          {rollup.inFlight > 0 ? (
            <li>{t("safeProcessing", { count: rollup.inFlight })}</li>
          ) : null}
          {rollup.needsAttention > 0 ? (
            <li>{t("safeAttention", { count: rollup.needsAttention })}</li>
          ) : null}
          {rollup.ready > 0 ? (
            <li>{t("safeAllReady", { count: rollup.ready })}</li>
          ) : null}
          {lastCheckedAt !== null ? (
            <li className="text-[var(--color-text-muted)]">
              {t("lastChecked", {
                when: new Date(lastCheckedAt).toLocaleTimeString(locale, {
                  hour: "2-digit",
                  minute: "2-digit",
                }),
              })}
            </li>
          ) : null}
        </ul>

        {/* The badge repeats the state in a word, so the tint is never the
            only carrier of meaning. */}
        <p
          className={cn(
            "mt-4 inline-flex h-8 items-center rounded-[var(--radius-md)] px-3 text-[12px] font-semibold",
            overall === "warning"
              ? "bg-[var(--color-primary-hover)] text-white"
              : overall === "working"
                ? "bg-[var(--color-cream)] text-[var(--color-primary-text)]"
                : "bg-[var(--color-success-light)] text-[var(--color-success)]"
          )}
        >
          {t(
            overall === "warning"
              ? "stateWarning"
              : overall === "working"
                ? "stateWorking"
                : "stateOk"
          )}
        </p>

        <p className="mt-3 text-[13px] leading-relaxed text-[var(--color-text-muted)]">
          {t("processingContinues")}
        </p>
      </section>
    </aside>
  );
}
