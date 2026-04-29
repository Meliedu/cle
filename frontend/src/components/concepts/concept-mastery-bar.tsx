"use client";

interface Props {
  readonly conceptName: string;
  readonly mastery: number;       // 0..1
  readonly confidence: number;    // 0..1
  readonly attempts: number;
}

export function ConceptMasteryBar({
  conceptName,
  mastery,
  confidence,
  attempts,
}: Props) {
  // 95% Beta CI is approximated by mean ± 1.96 * sqrt(var); we already have
  // confidence = 1 - sqrt(var), so var = (1 - confidence)^2.
  const stdDev = Math.max(0, 1 - confidence);
  const lo = Math.max(0, mastery - 1.96 * stdDev);
  const hi = Math.min(1, mastery + 1.96 * stdDev);

  const percent = (n: number) => `${Math.round(n * 100)}%`;

  return (
    <article
      className="space-y-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
      data-testid="concept-mastery-bar"
    >
      <header className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-[var(--color-text)]">
          {conceptName}
        </h3>
        <span className="text-xs text-[var(--color-muted)]">
          {attempts} attempt{attempts === 1 ? "" : "s"}
        </span>
      </header>
      <div
        role="meter"
        aria-valuenow={Math.round(mastery * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${conceptName} mastery: ${percent(mastery)}`}
        className="relative h-2 overflow-hidden rounded bg-[var(--color-bg)]"
      >
        {/* CI band */}
        <div
          className="absolute top-0 h-full bg-[var(--color-accent-soft)]"
          style={{
            left: `${lo * 100}%`,
            width: `${(hi - lo) * 100}%`,
          }}
        />
        {/* Mean marker */}
        <div
          className="absolute top-0 h-full w-0.5 bg-[var(--color-accent)]"
          style={{ left: `${mastery * 100}%` }}
        />
      </div>
      <p className="text-xs text-[var(--color-muted)]">
        {percent(mastery)} mastery (95% CI {percent(lo)}–{percent(hi)})
      </p>
    </article>
  );
}
