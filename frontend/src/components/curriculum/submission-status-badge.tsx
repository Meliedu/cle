import type { SubmissionStatus } from "@/lib/curriculum-types";

interface Props {
  readonly status: SubmissionStatus;
}

const STYLES: Record<SubmissionStatus, string> = {
  not_started: "bg-stone-200 text-stone-700",
  in_progress: "bg-amber-100 text-amber-800",
  submitted: "bg-blue-100 text-blue-800",
  late: "bg-rose-100 text-rose-800",
  graded: "bg-emerald-100 text-emerald-800",
  excused: "bg-stone-100 text-stone-600",
};

export function SubmissionStatusBadge({ status }: Props) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs ${STYLES[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}
