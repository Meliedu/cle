import { useAuth } from "@/hooks/use-auth";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

interface CourseOverview {
  readonly total_students: number;
  readonly avg_quiz_score: number | null;
  readonly total_quiz_attempts: number;
  readonly active_students_7d: number;
}

interface QuizStats {
  readonly quiz_id: string;
  readonly title: string;
  readonly avg_score: number | null;
  readonly attempt_count: number;
  readonly is_published: boolean;
}

interface StudentStats {
  readonly user_id: string;
  readonly full_name: string | null;
  readonly xp_points: number;
  readonly quizzes_completed: number;
  readonly avg_quiz_score: number | null;
  readonly flashcards_reviewed: number;
  readonly last_activity_date: string | null;
}

export function useCourseOverview(courseId: string) {
  const { getToken, isSignedIn } = useAuth();
  return useQuery<CourseOverview>({
    queryKey: ["analytics", "overview", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<{ data: CourseOverview }>(
        `/analytics/courses/${courseId}/overview`,
        { token }
      );
      return res.data;
    },
    enabled: isSignedIn === true,
  });
}

export function useQuizStats(courseId: string) {
  const { getToken, isSignedIn } = useAuth();
  return useQuery<QuizStats[]>({
    queryKey: ["analytics", "quizzes", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<{ data: QuizStats[] }>(
        `/analytics/courses/${courseId}/quizzes`,
        { token }
      );
      return res.data;
    },
    enabled: isSignedIn === true,
  });
}

export function useStudentStats(courseId: string) {
  const { getToken, isSignedIn } = useAuth();
  return useQuery<StudentStats[]>({
    queryKey: ["analytics", "students", courseId],
    queryFn: async () => {
      const token = await getToken({ template: "backend" });
      if (!token) throw new Error("Not authenticated");
      const res = await apiFetch<{ data: StudentStats[] }>(
        `/analytics/courses/${courseId}/students`,
        { token }
      );
      return res.data;
    },
    enabled: isSignedIn === true,
  });
}
