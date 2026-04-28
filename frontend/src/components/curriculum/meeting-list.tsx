"use client";

import { useState, useCallback } from "react";
import { useMeetings, useDeleteMeeting } from "@/hooks/use-meetings";
import { MeetingForm } from "./meeting-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Pencil, Trash2, Plus, X } from "lucide-react";
import type { CourseMeeting, MeetingStatus } from "@/lib/curriculum-types";

interface Props {
  readonly courseId: string;
}

function meetingStatusBadge(status: MeetingStatus) {
  switch (status) {
    case "planned":
      return (
        <span className="inline-block rounded px-2 py-0.5 text-xs bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
          planned
        </span>
      );
    case "in_progress":
      return (
        <span className="inline-block rounded px-2 py-0.5 text-xs bg-[var(--color-warning-light)] text-[var(--color-warning)] border border-[var(--color-warning)]">
          in progress
        </span>
      );
    case "taught":
      return (
        <span className="inline-block rounded px-2 py-0.5 text-xs bg-[var(--color-accent-light)] text-[var(--color-accent)] border border-[var(--color-accent)]">
          taught
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-block rounded px-2 py-0.5 text-xs bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)] line-through">
          cancelled
        </span>
      );
  }
}

export function MeetingList({ courseId }: Props) {
  const { data: meetings, isLoading } = useMeetings(courseId);
  const deleteMeeting = useDeleteMeeting(courseId);

  const [showAdd, setShowAdd] = useState(false);
  const [editingMeeting, setEditingMeeting] = useState<CourseMeeting | null>(null);

  const handleDelete = useCallback(
    async (meeting: CourseMeeting) => {
      const label = meeting.title ?? `Meeting ${meeting.meeting_index}`;
      if (!window.confirm(`Delete "${label}"?`)) return;
      try {
        await deleteMeeting.mutateAsync(meeting.id);
      } catch {
        // mutation error handled silently
      }
    },
    [deleteMeeting]
  );

  const sorted = [...(meetings ?? [])].sort(
    (a, b) =>
      new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime()
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--color-text)]">
          Meetings ({isLoading ? "..." : sorted.length})
        </h2>
        {!showAdd && (
          <Button
            size="sm"
            onClick={() => {
              setEditingMeeting(null);
              setShowAdd(true);
            }}
          >
            <Plus className="size-4" />
            Add meeting
          </Button>
        )}
      </div>

      {/* Add form panel */}
      {showAdd && !editingMeeting && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">New Meeting</CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)}>
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <MeetingForm
              courseId={courseId}
              onClose={() => setShowAdd(false)}
            />
          </CardContent>
        </Card>
      )}

      {/* Edit form panel */}
      {editingMeeting && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Edit Meeting</CardTitle>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setEditingMeeting(null)}
              >
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <MeetingForm
              courseId={courseId}
              meeting={editingMeeting}
              onClose={() => setEditingMeeting(null)}
            />
          </CardContent>
        </Card>
      )}

      {/* List */}
      <Card>
        <CardContent className="pt-4">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded-[var(--radius-md)]" />
              ))}
            </div>
          ) : sorted.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No meetings scheduled yet.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--color-border)]">
              {sorted.map((mtg) => (
                <li
                  key={mtg.id}
                  className="flex items-start gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-[var(--color-text)]">
                        {mtg.title ?? `Meeting ${mtg.meeting_index}`}
                      </span>
                      {meetingStatusBadge(mtg.status)}
                    </div>
                    <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                      {new Date(mtg.scheduled_at).toLocaleString()} &middot;{" "}
                      {mtg.duration_minutes} min
                      {mtg.location ? ` · ${mtg.location}` : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setShowAdd(false);
                        setEditingMeeting(mtg);
                      }}
                      aria-label={`Edit meeting ${mtg.meeting_index}`}
                    >
                      <Pencil className="size-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(mtg)}
                      disabled={deleteMeeting.isPending}
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-error)]"
                      aria-label={`Delete meeting ${mtg.meeting_index}`}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
