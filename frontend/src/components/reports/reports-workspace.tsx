"use client";

import { useState } from "react";

import { ReportArchive } from "./report-archive";
import { ReportDetail } from "./report-detail";

interface ReportsWorkspaceProps {
  readonly courseId: string;
}

/**
 * Client orchestrator for the teacher reports tab: the T080 archive and the
 * T081/T082 detail are two views of the same surface, switched by a selected
 * report id held in local state (no route change — the archive scroll + filter
 * state survive a round-trip to a report and back).
 */
export function ReportsWorkspace({ courseId }: ReportsWorkspaceProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (selectedId) {
    return (
      <ReportDetail
        courseId={courseId}
        reportId={selectedId}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return <ReportArchive courseId={courseId} onSelect={setSelectedId} />;
}
