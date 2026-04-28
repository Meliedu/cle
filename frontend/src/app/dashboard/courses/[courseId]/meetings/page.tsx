import { MeetingList } from "@/components/curriculum/meeting-list";

export default async function MeetingsPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">Meetings</h1>
      <MeetingList courseId={courseId} />
    </div>
  );
}
