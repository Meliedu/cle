"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Check, Rocket, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { PageHeader, StateBanner } from "@/components/patterns";
import {
  useCreateActivity,
  usePublishActivity,
  useUpdateActivity,
  type Activity,
  type ActivityFormat,
} from "@/hooks/use-activities";
import { ScorePolicyError } from "@/hooks/use-quizzes";

import { ACTIVITY_FORMAT_META, buildConfig, readConfigList } from "./activity-format";
import { StringListEditor } from "./string-list-editor";
import { ActivityPublishGate } from "./activity-publish-gate";
import {
  ActivityScorePolicyFields,
  type ScorePolicyValue,
} from "./activity-score-policy-fields";

interface ActivityBuilderProps {
  readonly courseId: string;
  /** Format for a NEW activity (ignored when `activity` is provided). */
  readonly format: ActivityFormat;
  /** Existing activity to edit; omit to author a fresh one. */
  readonly activity?: Activity;
  /** Called after a successful create/update/publish. */
  readonly onSaved?: (activity: Activity) => void;
  /** Optional back / cancel affordance. */
  readonly onBack?: () => void;
}

function initialPolicy(activity?: Activity): ScorePolicyValue {
  return {
    score_bearing: activity?.score_bearing ?? false,
    score_category_id: activity?.score_category_id ?? null,
    points: activity?.points ?? null,
    grading_mode: activity?.grading_mode ?? null,
    late_rule: activity?.late_rule ?? null,
    due_at: activity?.due_at ?? null,
    close_at: activity?.close_at ?? null,
  };
}

/**
 * T068–T071 — a single format-driven activity builder (swipe / vote /
 * comment_reaction). The active `format` selects which config array is edited
 * (`prompts | options | reactions`) and every save writes that array back into
 * `config` via `useCreateActivity` / `useUpdateActivity`. A score-bearing
 * activity surfaces the score-policy panel; publishing a score-bearing activity
 * that is missing fields throws `ScorePolicyError`, which the OWN
 * `ActivityPublishGate` renders as a blocked banner (also 422
 * `ACTIVITY_CONFIG_INVALID` + 409 `ACTIVITY_NOT_PUBLISHABLE`).
 */
export function ActivityBuilder({
  courseId,
  format,
  activity,
  onSaved,
  onBack,
}: ActivityBuilderProps) {
  const t = useTranslations("teacher.activities.builder");
  const tf = useTranslations("teacher.activities.formats");
  const meta = ACTIVITY_FORMAT_META[activity?.format ?? format];

  const [saved, setSaved] = useState<Activity | undefined>(activity);
  const [title, setTitle] = useState(activity?.title ?? "");
  const [items, setItems] = useState<readonly string[]>(
    activity ? readConfigList(activity) : []
  );
  const [anonymous, setAnonymous] = useState(activity?.anonymous ?? false);
  const [policy, setPolicy] = useState<ScorePolicyValue>(initialPolicy(activity));

  const createActivity = useCreateActivity(courseId);
  const updateActivity = useUpdateActivity(courseId);
  const publishActivity = usePublishActivity(courseId);

  const publishError = publishActivity.error;
  const missingFields = useMemo(
    () => (publishError instanceof ScorePolicyError ? publishError.missing : []),
    [publishError]
  );

  const activityId = saved?.id ?? null;
  const isBusy =
    createActivity.isPending || updateActivity.isPending || publishActivity.isPending;
  const canSave = title.trim().length > 0 && items.length > 0 && !isBusy;
  const published = saved?.status === "published" || saved?.status === "live";

  const persist = async (): Promise<Activity | undefined> => {
    const config = buildConfig(meta.format, items);
    const shared = {
      title: title.trim(),
      config,
      anonymous,
      score_bearing: policy.score_bearing,
      score_category_id: policy.score_bearing ? policy.score_category_id : null,
      points: policy.score_bearing ? policy.points : null,
      grading_mode: policy.score_bearing ? policy.grading_mode : null,
      late_rule: policy.score_bearing ? policy.late_rule : null,
      due_at: policy.due_at,
      close_at: policy.close_at,
    };
    try {
      const next = activityId
        ? await updateActivity.mutateAsync({ activityId, ...shared })
        : await createActivity.mutateAsync({ format: meta.format, ...shared });
      setSaved(next);
      onSaved?.(next);
      return next;
    } catch {
      return undefined;
    }
  };

  const handlePublish = async (): Promise<void> => {
    const current = await persist();
    if (!current) return;
    publishActivity.reset();
    try {
      const next = await publishActivity.mutateAsync(current.id);
      setSaved(next);
      onSaved?.(next);
    } catch {
      /* surfaced by ActivityPublishGate via publishActivity.error */
    }
  };

  const saveFailed = createActivity.isError || updateActivity.isError;

  return (
    <div className="space-y-6">
      <PageHeader
        as="h2"
        title={activity ? t("editTitle") : t("createTitle", { format: tf(meta.labelKey) })}
        description={t(`hint.${meta.format}`)}
        breadcrumb={
          onBack ? (
            <button
              type="button"
              onClick={onBack}
              className="text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
            >
              {t("back")}
            </button>
          ) : undefined
        }
      />

      {published ? (
        <StateBanner
          tone="success"
          title={t("published.title")}
          reason={t("published.reason")}
        />
      ) : null}

      <ActivityPublishGate error={publishError} />

      {saveFailed ? (
        <StateBanner
          tone="warning"
          title={t("saveError.title")}
          reason={t("saveError.reason")}
        />
      ) : null}

      <section className="space-y-4 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
        <div className="space-y-1.5">
          <Label htmlFor="activity-title" className="text-[13px] font-medium text-[var(--color-text)]">
            {t("titleLabel")}
          </Label>
          <Input
            id="activity-title"
            value={title}
            placeholder={t("titlePlaceholder")}
            onChange={(e) => setTitle(e.target.value)}
            className="h-9"
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <meta.Icon aria-hidden="true" className="size-4 text-[var(--color-primary)]" />
            <Label className="text-[13px] font-medium text-[var(--color-text)]">
              {t(`configLabel.${meta.format}`)}
            </Label>
          </div>
          <StringListEditor
            items={items}
            onChange={setItems}
            addPlaceholder={t(`addPlaceholder.${meta.format}`)}
            itemLabel={(i) => t(`itemLabel.${meta.format}`, { index: i + 1 })}
            emptyTitle={t(`configEmpty.${meta.format}.title`)}
            emptyReason={t(`configEmpty.${meta.format}.reason`)}
          />
        </div>

        <div className="flex items-center justify-between gap-4 border-t border-[var(--color-border)]/70 pt-4">
          <div className="space-y-0.5">
            <p className="text-[13px] font-medium text-[var(--color-text)]">
              {t("anonymous.label")}
            </p>
            <p className="text-[12px] text-[var(--color-text-secondary)]">
              {t("anonymous.hint")}
            </p>
          </div>
          <Switch
            checked={anonymous}
            onCheckedChange={setAnonymous}
            aria-label={t("anonymous.label")}
          />
        </div>
      </section>

      <ActivityScorePolicyFields
        courseId={courseId}
        value={policy}
        onChange={setPolicy}
        missing={missingFields}
      />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => void persist()}
          disabled={!canSave}
        >
          <Save />
          {t("actions.save")}
        </Button>
        <Button
          type="button"
          onClick={() => void handlePublish()}
          disabled={!canSave}
        >
          {published ? <Check /> : <Rocket />}
          {published ? t("actions.republish") : t("actions.publish")}
        </Button>
      </div>
    </div>
  );
}
