import { ConceptClusterQueue } from "@/components/concepts/concept-cluster-queue";

export default async function ConceptCurationPage(props: {
  params: Promise<{ courseId: string }>;
}) {
  const { courseId } = await props.params;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-2xl font-semibold text-[var(--color-text)]">
        Concept Curation
      </h1>
      <p className="text-sm text-[var(--color-muted)]">
        Review extracted concept candidates. Approve, rename, merge into an
        existing concept, or reject.
      </p>
      <ConceptClusterQueue courseId={courseId} />
    </div>
  );
}
