"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";

export type GenerationJobKind =
  | "generate_quiz"
  | "generate_flashcards"
  | "generate_summary";

export type GenerationJobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface GenerationJobResult {
  readonly quiz_id?: string;
  readonly flashcard_set_id?: string;
  readonly summary_id?: string;
  readonly question_count?: number;
  readonly card_count?: number;
}

export interface GenerationJob {
  readonly jobId: string;
  readonly kind: GenerationJobKind;
  readonly courseId: string;
  readonly title: string | null;
  readonly status: GenerationJobStatus;
  readonly result: GenerationJobResult | null;
  readonly error: string | null;
  readonly startedAt: number;
}

interface GenerationJobStore {
  readonly jobs: readonly GenerationJob[];
  readonly trackJob: (initial: {
    jobId: string;
    kind: GenerationJobKind;
    courseId: string;
    title: string | null;
  }) => void;
  readonly dismissJob: (jobId: string) => void;
  /** Remove all completed / failed jobs from the dock. Leaves active ones. */
  readonly dismissAllFinished: () => void;
}

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_MS = 5 * 60 * 1000; // 5 minutes — hard ceiling
const KIND_LABEL: Record<GenerationJobKind, string> = {
  generate_quiz: "Quiz",
  generate_flashcards: "Flashcards",
  generate_summary: "Summary",
};

type Action =
  | { type: "add"; job: GenerationJob }
  | { type: "update"; jobId: string; patch: Partial<GenerationJob> }
  | { type: "dismiss"; jobId: string }
  | { type: "dismiss-finished" };

function reducer(
  state: readonly GenerationJob[],
  action: Action
): readonly GenerationJob[] {
  switch (action.type) {
    case "add": {
      if (state.some((j) => j.jobId === action.job.jobId)) return state;
      return [...state, action.job];
    }
    case "update":
      return state.map((j) =>
        j.jobId === action.jobId ? { ...j, ...action.patch } : j
      );
    case "dismiss":
      return state.filter((j) => j.jobId !== action.jobId);
    case "dismiss-finished":
      return state.filter(
        (j) => j.status === "pending" || j.status === "running"
      );
  }
}

const GenerationJobsContext = createContext<GenerationJobStore | null>(null);

interface StatusEnvelope {
  readonly success: boolean;
  readonly data: {
    readonly job_id: string;
    readonly kind: GenerationJobKind;
    readonly status: GenerationJobStatus;
    readonly course_id: string;
    readonly title: string | null;
    readonly result: GenerationJobResult | null;
    readonly error: string | null;
  };
}

export function GenerationJobsProvider({ children }: { children: ReactNode }) {
  const [jobs, dispatch] = useReducer(reducer, [] as readonly GenerationJob[]);
  const { getToken, isSignedIn } = useAuth();
  const queryClient = useQueryClient();
  const pollersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map()
  );
  const toastedRef = useRef<Set<string>>(new Set());

  const trackJob = useCallback<GenerationJobStore["trackJob"]>(
    ({ jobId, kind, courseId, title }) => {
      dispatch({
        type: "add",
        job: {
          jobId,
          kind,
          courseId,
          title,
          status: "pending",
          result: null,
          error: null,
          startedAt: Date.now(),
        },
      });
    },
    []
  );

  const dismissJob = useCallback<GenerationJobStore["dismissJob"]>(
    (jobId) => {
      const t = pollersRef.current.get(jobId);
      if (t) clearTimeout(t);
      pollersRef.current.delete(jobId);
      dispatch({ type: "dismiss", jobId });
    },
    []
  );

  const dismissAllFinished = useCallback<
    GenerationJobStore["dismissAllFinished"]
  >(() => {
    dispatch({ type: "dismiss-finished" });
  }, []);

  // Start / stop pollers as jobs enter and leave the store.
  useEffect(() => {
    if (!isSignedIn) return;

    const active = jobs.filter(
      (j) => j.status === "pending" || j.status === "running"
    );

    for (const job of active) {
      if (pollersRef.current.has(job.jobId)) continue;

      const poll = async () => {
        if (Date.now() - job.startedAt > MAX_POLL_MS) {
          dispatch({
            type: "update",
            jobId: job.jobId,
            patch: {
              status: "failed",
              error: "Timed out waiting for generation to finish.",
            },
          });
          return;
        }

        try {
          const token = await getToken({ template: "backend" });
          if (!token) throw new Error("Not authenticated");

          const response = await apiFetch<StatusEnvelope>(
            `/rag/jobs/${job.jobId}`,
            { method: "GET", token }
          );
          const data = response.data;

          dispatch({
            type: "update",
            jobId: job.jobId,
            patch: {
              status: data.status,
              result: data.result,
              error: data.error,
            },
          });

          if (data.status === "completed" || data.status === "failed") {
            return; // stop polling
          }
        } catch (err) {
          // Transient network error — keep polling, surface in dock if persistent
          dispatch({
            type: "update",
            jobId: job.jobId,
            patch: {
              error: err instanceof Error ? err.message : "Network error",
            },
          });
        }

        const t = setTimeout(poll, POLL_INTERVAL_MS);
        pollersRef.current.set(job.jobId, t);
      };

      const t = setTimeout(poll, POLL_INTERVAL_MS);
      pollersRef.current.set(job.jobId, t);
    }

    // Cleanup: if a job left the active set, clear its poller.
    const activeIds = new Set(active.map((j) => j.jobId));
    for (const [id, t] of pollersRef.current.entries()) {
      if (!activeIds.has(id)) {
        clearTimeout(t);
        pollersRef.current.delete(id);
      }
    }
  }, [jobs, getToken, isSignedIn]);

  // Fire toasts on terminal transitions and invalidate caches.
  useEffect(() => {
    for (const job of jobs) {
      if (toastedRef.current.has(job.jobId)) continue;
      if (job.status !== "completed" && job.status !== "failed") continue;

      toastedRef.current.add(job.jobId);

      const kindLabel = KIND_LABEL[job.kind];
      const displayTitle = job.title ? ` "${job.title}"` : "";

      if (job.status === "completed") {
        toast.success(`${kindLabel}${displayTitle} ready`, {
          description: "Click to open",
          action: job.result
            ? {
                label: "Open",
                onClick: () => handleOpen(job),
              }
            : undefined,
          duration: 10_000,
        });

        // Invalidate the relevant list so the user's current page updates.
        if (job.kind === "generate_quiz") {
          queryClient.invalidateQueries({
            queryKey: ["quizzes", job.courseId],
          });
        } else if (job.kind === "generate_flashcards") {
          queryClient.invalidateQueries({
            queryKey: ["flashcards", job.courseId],
          });
        } else if (job.kind === "generate_summary") {
          queryClient.invalidateQueries({
            queryKey: ["course-summary", job.courseId],
          });
        }
      } else {
        toast.error(`${kindLabel}${displayTitle} failed`, {
          description: job.error ?? "Unknown error",
          duration: 10_000,
        });
      }
    }
  }, [jobs, queryClient]);

  const value = useMemo<GenerationJobStore>(
    () => ({ jobs, trackJob, dismissJob, dismissAllFinished }),
    [jobs, trackJob, dismissJob, dismissAllFinished]
  );

  return (
    <GenerationJobsContext.Provider value={value}>
      {children}
    </GenerationJobsContext.Provider>
  );
}

function handleOpen(job: GenerationJob) {
  if (!job.result) return;
  // encodeURIComponent each id segment so any stray path or query character
  // in a course/quiz/flashcard id can never break out of the intended
  // dashboard route.
  const courseId = encodeURIComponent(job.courseId);
  if (job.kind === "generate_quiz" && job.result.quiz_id) {
    const quizId = encodeURIComponent(job.result.quiz_id);
    window.location.href = `/dashboard/courses/${courseId}/quizzes/${quizId}`;
    return;
  }
  if (job.kind === "generate_flashcards" && job.result.flashcard_set_id) {
    const setId = encodeURIComponent(job.result.flashcard_set_id);
    window.location.href = `/dashboard/courses/${courseId}/flashcards/${setId}`;
    return;
  }
  if (job.kind === "generate_summary") {
    window.location.href = `/dashboard/courses/${courseId}`;
  }
}

export function useGenerationJobs(): GenerationJobStore {
  const ctx = useContext(GenerationJobsContext);
  if (!ctx) {
    throw new Error(
      "useGenerationJobs must be used within <GenerationJobsProvider>"
    );
  }
  return ctx;
}
