"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Users,
  BarChart3,
  Target,
  Activity,
} from "lucide-react";
import {
  useCourseOverview,
  useQuizStats,
  useStudentStats,
} from "@/hooks/use-analytics";

interface CourseAnalyticsProps {
  readonly courseId: string;
}

export function CourseAnalytics({ courseId }: CourseAnalyticsProps) {
  const { data: overview, isLoading: overviewLoading } = useCourseOverview(courseId);
  const { data: quizStats, isLoading: quizLoading } = useQuizStats(courseId);
  const { data: studentStats, isLoading: studentsLoading } = useStudentStats(courseId);

  return (
    <div className="space-y-6">
      {/* Overview cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<Users className="size-5" />}
          label="Students"
          value={overview?.total_students}
          isLoading={overviewLoading}
        />
        <StatCard
          icon={<BarChart3 className="size-5" />}
          label="Avg Quiz Score"
          value={overview?.avg_quiz_score != null ? `${overview.avg_quiz_score}%` : undefined}
          isLoading={overviewLoading}
        />
        <StatCard
          icon={<Target className="size-5" />}
          label="Quiz Attempts"
          value={overview?.total_quiz_attempts}
          isLoading={overviewLoading}
        />
        <StatCard
          icon={<Activity className="size-5" />}
          label="Active (7d)"
          value={overview?.active_students_7d}
          isLoading={overviewLoading}
        />
      </div>

      {/* Quiz performance */}
      <Card>
        <CardHeader>
          <CardTitle>Quiz Performance</CardTitle>
        </CardHeader>
        <CardContent>
          {quizLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : !quizStats || quizStats.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No quizzes created yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-text-muted)]">
                    <th className="pb-2 pr-4 font-medium">Quiz</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 pr-4 font-medium text-right">Avg Score</th>
                    <th className="pb-2 font-medium text-right">Attempts</th>
                  </tr>
                </thead>
                <tbody>
                  {quizStats.map((quiz) => (
                    <tr
                      key={quiz.quiz_id}
                      className="border-b border-[var(--color-border)] last:border-0"
                    >
                      <td className="py-2.5 pr-4 font-medium text-[var(--color-text)]">
                        {quiz.title}
                      </td>
                      <td className="py-2.5 pr-4">
                        <Badge
                          variant="outline"
                          className={
                            quiz.is_published
                              ? "border-[var(--color-success)] text-[var(--color-success)]"
                              : "border-[var(--color-warning)] text-[var(--color-warning)]"
                          }
                        >
                          {quiz.is_published ? "Published" : "Draft"}
                        </Badge>
                      </td>
                      <td className="py-2.5 pr-4 text-right text-[var(--color-text-secondary)]">
                        {quiz.avg_score != null ? `${quiz.avg_score}%` : "—"}
                      </td>
                      <td className="py-2.5 text-right text-[var(--color-text-secondary)]">
                        {quiz.attempt_count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Student table */}
      <Card>
        <CardHeader>
          <CardTitle>Students</CardTitle>
        </CardHeader>
        <CardContent>
          {studentsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : !studentStats || studentStats.length === 0 ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              No students enrolled yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-xs text-[var(--color-text-muted)]">
                    <th className="pb-2 pr-4 font-medium">Name</th>
                    <th className="pb-2 pr-4 font-medium text-right">XP</th>
                    <th className="pb-2 pr-4 font-medium text-right">Quizzes</th>
                    <th className="pb-2 pr-4 font-medium text-right">Avg Score</th>
                    <th className="pb-2 pr-4 font-medium text-right">Flashcards</th>
                    <th className="pb-2 font-medium text-right">Last Active</th>
                  </tr>
                </thead>
                <tbody>
                  {studentStats.map((student) => (
                    <tr
                      key={student.user_id}
                      className="border-b border-[var(--color-border)] last:border-0"
                    >
                      <td className="py-2.5 pr-4">
                        <div>
                          <p className="font-medium text-[var(--color-text)]">
                            {student.full_name ?? "—"}
                          </p>
                          <p className="text-xs text-[var(--color-text-muted)]">
                            {student.email}
                          </p>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-medium text-[var(--color-primary)]">
                        {student.xp_points.toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-[var(--color-text-secondary)]">
                        {student.quizzes_completed}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-[var(--color-text-secondary)]">
                        {student.avg_quiz_score != null
                          ? `${student.avg_quiz_score}%`
                          : "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-right text-[var(--color-text-secondary)]">
                        {student.flashcards_reviewed}
                      </td>
                      <td className="py-2.5 text-right text-[var(--color-text-muted)]">
                        {student.last_activity_date ?? "Never"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  isLoading,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number | undefined;
  isLoading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-primary-light)] text-[var(--color-primary)]">
          {icon}
        </div>
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">{label}</p>
          {isLoading ? (
            <Skeleton className="h-7 w-10" />
          ) : (
            <p className="text-xl font-bold text-[var(--color-text)]">
              {value ?? "—"}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
