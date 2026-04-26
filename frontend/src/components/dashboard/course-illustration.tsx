interface CourseIllustrationProps {
  readonly seed: string;
  readonly language: string;
  readonly className?: string;
}

interface Palette {
  readonly bg: string;
  readonly accent: string;
  readonly ink: string;
}

const PALETTES: readonly Palette[] = [
  {
    bg: "oklch(88% 0.07 35)",
    accent: "oklch(75% 0.13 35)",
    ink: "oklch(30% 0.05 35)",
  },
  {
    bg: "oklch(92% 0.06 75)",
    accent: "oklch(78% 0.14 75)",
    ink: "oklch(28% 0.03 65)",
  },
  {
    bg: "oklch(86% 0.05 120)",
    accent: "oklch(58% 0.09 120)",
    ink: "oklch(25% 0.03 120)",
  },
  {
    bg: "oklch(90% 0.05 200)",
    accent: "oklch(68% 0.09 210)",
    ink: "oklch(28% 0.04 220)",
  },
  {
    bg: "oklch(89% 0.05 20)",
    accent: "oklch(68% 0.13 20)",
    ink: "oklch(28% 0.05 20)",
  },
];

function seedHash(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return h;
}

/**
 * Soft flat illustration that stands in for per-course cover art until
 * real cover uploads ship. Deterministic per course id so it feels stable.
 */
export function CourseIllustration({
  seed,
  language,
  className,
}: CourseIllustrationProps) {
  const hash = seedHash(seed);
  const palette = PALETTES[hash % PALETTES.length];
  const variant = hash % 3;
  const glyph = language.trim().slice(0, 2).toUpperCase() || "··";

  return (
    <div
      className={className}
      style={{ backgroundColor: palette.bg }}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 120 120"
        preserveAspectRatio="xMidYMid slice"
        className="size-full"
      >
        {variant === 0 ? (
          <>
            <circle cx="28" cy="90" r="34" fill={palette.accent} opacity="0.55" />
            <rect
              x="62"
              y="20"
              width="48"
              height="48"
              rx="8"
              fill={palette.accent}
              opacity="0.8"
            />
            <circle cx="96" cy="92" r="14" fill={palette.ink} opacity="0.85" />
          </>
        ) : null}
        {variant === 1 ? (
          <>
            <path
              d="M-5 80 Q 40 40 75 70 T 130 60 L 130 130 L -5 130 Z"
              fill={palette.accent}
              opacity="0.7"
            />
            <circle cx="35" cy="40" r="14" fill={palette.ink} opacity="0.8" />
            <rect
              x="80"
              y="18"
              width="28"
              height="8"
              rx="4"
              fill={palette.ink}
              opacity="0.5"
            />
          </>
        ) : null}
        {variant === 2 ? (
          <>
            <circle cx="60" cy="60" r="44" fill={palette.accent} opacity="0.6" />
            <path
              d="M20 60 H100 M60 20 V100"
              stroke={palette.ink}
              strokeWidth="3"
              strokeLinecap="round"
              opacity="0.55"
            />
            <circle cx="60" cy="60" r="10" fill={palette.ink} />
          </>
        ) : null}

        <text
          x="60"
          y="64"
          textAnchor="middle"
          fontFamily="var(--font-sans), sans-serif"
          fontSize="26"
          fontWeight="700"
          fill={palette.ink}
          style={{ letterSpacing: "0.04em" }}
        >
          {glyph}
        </text>
      </svg>
    </div>
  );
}
