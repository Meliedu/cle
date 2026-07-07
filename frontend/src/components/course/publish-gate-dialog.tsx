"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, CircleAlert, Loader2, Rocket } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StateBanner } from "@/components/patterns";
import { ApiError } from "@/lib/api";
import {
  usePublishCheckpoint,
  type Checkpoint,
  type CloseRule,
} from "@/hooks/use-checkpoints";

const CLOSE_RULES: readonly CloseRule[] = [
  "end_of_session",
  "at_close_at",
  "manual",
];

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40";
const INPUT_CLASS = SELECT_CLASS;

interface PublishGateDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly courseId: string;
  readonly checkpoint: Checkpoint;
  readonly onPublished?: () => void;
}

/** One gate requirement + whether the current checkpoint satisfies it. */
interface Requirement {
  readonly key: string;
  readonly met: boolean;
}

/**
 * T044 — publish-checkpoint confirmation. Confirms an immediate release, letting
 * the teacher pick the close rule first. On a 409 `REVIEW_REQUIRED` (the §3.4
 * publish gate — no session attached, or missing release timing) it surfaces the
 * refusal as a `StateBanner tone="blocked"` with the server reason plus a
 * derived checklist of what publishing needs, mirroring the setup missing-source
 * gate. Only offered for `approved`/`scheduled` checkpoints (the lifecycle panel
 * gates the trigger).
 */
export function PublishGateDialog({
  open,
  onOpenChange,
  courseId,
  checkpoint,
  onPublished,
}: PublishGateDialogProps) {
  const t = useTranslations("teacher.checkpoint.publish");
  const publish = usePublishCheckpoint(courseId, checkpoint.id);
  const [closeRule, setCloseRule] = useState<CloseRule>("end_of_session");
  const [closeAt, setCloseAt] = useState("");
  const [gateError, setGateError] = useState<string | null>(null);
  const [genericError, setGenericError] = useState(false);

  const requirements: readonly Requirement[] = [
    { key: "session", met: Boolean(checkpoint.meeting_id) },
  ];

  const confirm = useCallback(async () => {
    setGateError(null);
    setGenericError(false);
    const body = {
      release_at: new Date().toISOString(),
      close_rule: closeRule,
      close_at:
        closeRule === "at_close_at" && closeAt
          ? new Date(closeAt).toISOString()
          : null,
    };
    try {
      await publish.mutateAsync(body);
      onOpenChange(false);
      onPublished?.();
    } catch (error) {
      if (error instanceof ApiError && error.code === "REVIEW_REQUIRED") {
        setGateError(error.detail ?? t("gate.genericReason"));
      } else {
        setGenericError(true);
      }
    }
  }, [publish, closeRule, closeAt, onOpenChange, onPublished, t]);

  const closeAtInvalid = closeRule === "at_close_at" && !closeAt;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("subtitle")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <ul className="space-y-1.5" aria-label={t("requirementsLabel")}>
            {requirements.map((req) => (
              <li
                key={req.key}
                className="flex items-center gap-2 text-[13px] text-[var(--color-text-secondary)]"
              >
                {req.met ? (
                  <CheckCircle2
                    aria-hidden="true"
                    className="size-4 shrink-0 text-[var(--color-success)]"
                  />
                ) : (
                  <CircleAlert
                    aria-hidden="true"
                    className="size-4 shrink-0 text-[var(--color-error)]"
                  />
                )}
                <span>{t(`requirements.${req.key}`)}</span>
              </li>
            ))}
          </ul>

          <div className="space-y-1.5">
            <label
              htmlFor="publish-close-rule"
              className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
            >
              {t("closeRuleLabel")}
            </label>
            <select
              id="publish-close-rule"
              className={SELECT_CLASS}
              value={closeRule}
              onChange={(e) => setCloseRule(e.target.value as CloseRule)}
            >
              {CLOSE_RULES.map((rule) => (
                <option key={rule} value={rule}>
                  {t(`closeRule.${rule}`)}
                </option>
              ))}
            </select>
          </div>

          {closeRule === "at_close_at" ? (
            <div className="space-y-1.5">
              <label
                htmlFor="publish-close-at"
                className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
              >
                {t("closeAtLabel")}
              </label>
              <input
                id="publish-close-at"
                type="datetime-local"
                className={INPUT_CLASS}
                value={closeAt}
                onChange={(e) => setCloseAt(e.target.value)}
              />
            </div>
          ) : null}

          {gateError ? (
            <StateBanner
              tone="blocked"
              title={t("gate.title")}
              reason={gateError}
            />
          ) : null}
          {genericError ? (
            <p role="alert" className="text-[13px] text-[var(--color-error)]">
              {t("gate.generic")}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t("cancel")}
          </Button>
          <Button
            type="button"
            disabled={publish.isPending || closeAtInvalid}
            onClick={() => void confirm()}
          >
            {publish.isPending ? (
              <Loader2 aria-hidden="true" className="animate-spin" />
            ) : (
              <Rocket aria-hidden="true" />
            )}
            {t("confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
