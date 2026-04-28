"use client";

import { useRole } from "@/hooks/use-role";
import { AssignmentList } from "@/components/curriculum/assignment-list";
import { StudentAssignmentList } from "@/components/curriculum/student-assignment-list";

interface Props {
  readonly courseId: string;
}

export function AssignmentsRouter({ courseId }: Props) {
  const { isInstructor, isLoaded } = useRole();
  if (!isLoaded) return null;
  return isInstructor ? (
    <AssignmentList courseId={courseId} />
  ) : (
    <StudentAssignmentList courseId={courseId} />
  );
}
