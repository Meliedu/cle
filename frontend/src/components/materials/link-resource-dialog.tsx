"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { LinkIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { StateBanner } from "@/components/patterns";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const SELECT_CLASS =
  "h-9 w-full min-w-0 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 text-[13px] text-[var(--color-text)] outline-none transition-colors focus-visible:border-[var(--color-primary)] focus-visible:ring-3 focus-visible:ring-[var(--color-primary)]/40";

/** Minimal session shape needed to populate the folder select. */
export interface LinkSessionOption {
  readonly meetingId: string;
  readonly index: number;
  readonly title: string | null;
}

export interface LinkResourceDraft {
  readonly url: string;
  readonly title: string;
  readonly meetingId: string | null;
  readonly description: string;
}

interface LinkResourceDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly sessions: readonly LinkSessionOption[];
  /** Called with the validated draft. See the backend-limitation note below. */
  readonly onSubmit: (draft: LinkResourceDraft) => void;
}

function isValidHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * T053/T054 — "Add link" resource modal. Collects an external URL + metadata
 * and a target session.
 *
 * BACKEND LIMITATION: the documents API is file-only — there is no external-
 * link document type (P4 B8 covers assign / folders / preview, not link
 * bookmarks). Rather than fake a file upload of a URL, this modal is fully
 * designed and validated but carries an upfront notice that links aren't
 * persisted yet; on submit it hands the draft to `onSubmit` (the library shows
 * the same notice and closes). The moment a link-document endpoint exists this
 * only needs its `onSubmit` re-wired to a mutation — the form is complete.
 */
export function LinkResourceDialog({
  open,
  onOpenChange,
  sessions,
  onSubmit,
}: LinkResourceDialogProps) {
  const t = useTranslations("teacher.materials.link");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [meetingId, setMeetingId] = useState<string>("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);

  const urlValid = isValidHttpUrl(url.trim());
  const showUrlError = touched && url.trim().length > 0 && !urlValid;

  const handleSubmit = () => {
    setTouched(true);
    if (!urlValid) return;
    onSubmit({
      url: url.trim(),
      title: title.trim(),
      meetingId: meetingId || null,
      description: description.trim(),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("subtitle")}</DialogDescription>
        </DialogHeader>

        <StateBanner
          tone="info"
          title={t("unsupportedTitle")}
          reason={t("unsupportedBody")}
        />

        <div className="space-y-3">
          <Field
            id="link-url"
            label={t("urlLabel")}
            error={showUrlError ? t("urlInvalid") : undefined}
            required
          >
            <Input
              id="link-url"
              type="url"
              inputMode="url"
              value={url}
              placeholder={t("urlPlaceholder")}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={() => setTouched(true)}
              aria-invalid={showUrlError || undefined}
            />
          </Field>

          <Field id="link-title" label={t("nameLabel")}>
            <Input
              id="link-title"
              value={title}
              placeholder={t("namePlaceholder")}
              onChange={(e) => setTitle(e.target.value)}
            />
          </Field>

          <Field id="link-session" label={t("sessionLabel")}>
            <select
              id="link-session"
              className={SELECT_CLASS}
              value={meetingId}
              onChange={(e) => setMeetingId(e.target.value)}
            >
              <option value="">{t("sessionNone")}</option>
              {sessions.map((s) => (
                <option key={s.meetingId} value={s.meetingId}>
                  {s.title
                    ? `${s.index}. ${s.title}`
                    : String(s.index)}
                </option>
              ))}
            </select>
          </Field>

          <Field id="link-description" label={t("descriptionLabel")}>
            <Textarea
              id="link-description"
              rows={2}
              value={description}
              placeholder={t("descriptionPlaceholder")}
              onChange={(e) => setDescription(e.target.value)}
            />
          </Field>
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
            disabled={!urlValid}
            onClick={handleSubmit}
            data-icon="inline-start"
          >
            <LinkIcon aria-hidden="true" />
            {t("submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  id,
  label,
  error,
  required,
  children,
}: {
  readonly id: string;
  readonly label: string;
  readonly error?: string;
  readonly required?: boolean;
  readonly children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block text-[12px] font-medium text-[var(--color-text-secondary)]"
      >
        {label}
        {required ? (
          <span className="text-[var(--color-error)]"> *</span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-[11px] text-[var(--color-error)]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
