"use client";

const DIFFICULTY_LABELS = ["easy", "medium", "hard"] as const;
type Difficulty = (typeof DIFFICULTY_LABELS)[number];

interface TransitionMatrixProps {
  readonly matrix: Record<string, Record<string, number>>;
  readonly contentType: string;
}

function cellBackground(row: Difficulty, col: Difficulty, value: number): string {
  if (row === col) {
    // Diagonal — correct label: green intensity by value
    const intensity = Math.round(value * 100);
    if (intensity === 0) return "oklch(97% 0.01 145)";
    if (intensity < 30) return "oklch(93% 0.05 145)";
    if (intensity < 60) return "oklch(88% 0.08 145)";
    return "oklch(82% 0.12 145)";
  }
  // Off-diagonal — mislabeled: yellow/red by value
  if (value === 0) return "oklch(97% 0.01 80)";
  if (value < 0.15) return "oklch(95% 0.04 75)";
  if (value < 0.3) return "oklch(90% 0.08 50)";
  return "oklch(90% 0.05 25)";
}

function cellTextColor(row: Difficulty, col: Difficulty): string {
  if (row === col) return "var(--color-success)";
  return "var(--color-error)";
}

export function TransitionMatrix({ matrix, contentType }: TransitionMatrixProps) {
  const rows = DIFFICULTY_LABELS.filter((d) => matrix[d]);

  if (rows.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No transition data for {contentType}.
      </p>
    );
  }

  return (
    <div>
      <p className="mb-2 text-xs text-[var(--color-text-muted)]">
        Rows = LLM label &nbsp;·&nbsp; Columns = observed difficulty
      </p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              <th className="w-20 py-1 pr-3 text-right text-xs font-medium text-[var(--color-text-secondary)]">
                LLM \ Real
              </th>
              {DIFFICULTY_LABELS.map((col) => (
                <th
                  key={col}
                  className="px-3 py-1 text-center text-xs font-medium capitalize text-[var(--color-text-secondary)]"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DIFFICULTY_LABELS.map((row) => {
              const rowData = matrix[row] ?? {};
              return (
                <tr key={row}>
                  <td className="py-1 pr-3 text-right text-xs font-medium capitalize text-[var(--color-text-secondary)]">
                    {row}
                  </td>
                  {DIFFICULTY_LABELS.map((col) => {
                    const value = rowData[col] ?? 0;
                    const pct = Math.round(value * 100);
                    const bg = cellBackground(row, col, value);
                    const textColor = cellTextColor(row, col);
                    return (
                      <td
                        key={col}
                        className="px-3 py-2 text-center font-mono text-xs font-semibold"
                        style={{
                          backgroundColor: bg,
                          color: pct > 0 ? textColor : "var(--color-text-muted)",
                          borderRadius: "var(--radius-sm)",
                        }}
                      >
                        {pct}%
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
