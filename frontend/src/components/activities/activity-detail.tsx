"use client";

import { useState } from "react";

import type { Activity, ActivityFormat } from "@/hooks/use-activities";

import { ActivityBuilder } from "./activity-builder";
import { ActivityMonitor } from "./activity-monitor";
import { ActivityResults } from "./activity-results";

interface ActivityDetailProps {
  readonly courseId: string;
  /** Format for a new activity (ignored when `activity` is set). */
  readonly format: ActivityFormat;
  /** Existing activity to edit; omit to author a fresh one. */
  readonly activity?: Activity;
  readonly onBack: () => void;
}

/**
 * F5/F6 detail composition: the builder (F4), and — once the activity is
 * published — the live monitor (F5) plus the results / evidence table (F5).
 * Selecting an existing activity from the home lands here; a fresh one shows
 * only the builder until it is first published.
 */
export function ActivityDetail({ courseId, format, activity, onBack }: ActivityDetailProps) {
  const [current, setCurrent] = useState<Activity | undefined>(activity);

  const format_ = current?.format ?? format;
  const isLive = current?.status === "live";
  const isPublished =
    current?.status === "published" ||
    current?.status === "live" ||
    current?.status === "closed";

  return (
    <div className="space-y-8">
      <ActivityBuilder
        courseId={courseId}
        format={format_}
        activity={activity}
        onSaved={setCurrent}
        onBack={onBack}
      />

      {current && isPublished ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <ActivityMonitor
            activityId={current.id}
            format={format_}
            enabled={isLive}
          />
          <ActivityResults activityId={current.id} anonymous={current.anonymous} />
        </div>
      ) : null}
    </div>
  );
}
