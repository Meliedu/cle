"use client";

import { use } from "react";
import { useRole } from "@/hooks/use-role";
import { AssignmentList } from "@/components/curriculum/assignment-list";
import { StudentAssignmentList } from "@/components/curriculum/student-assignment-list";

function AssignmentsRouter({ courseId }: { readonly courseId: string }) {
  const { isInstructor, isLoaded } = useRole();
  if (!isLoaded) return null;
  return isInstructor ? (
    <AssignmentList courseId={courseId} />
  ) : (
    <StudentAssignmentList courseId={courseId} />
  );
}

export default function AssignmentsPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = use(props.params);
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Assignments
      </h1>
      <AssignmentsRouter courseId={courseId} />
    </div>
  );
}
