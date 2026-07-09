interface CourseIllustrationProps {
  readonly seed: string;
  readonly language: string;
  readonly className?: string;
}

interface Palette {
  readonly from: string;
  readonly to: string;
  readonly accent: string;
  readonly ink: string;
}

// Warm, cohesive gradient pairs drawn from the Honey & Salt family so cover
// art always feels part of the brand rather than a stock placeholder.
const PALETTES: readonly Palette[] = [
  { from: "oklch(90% 0.07 80)", to: "oklch(82% 0.11 65)", accent: "oklch(74% 0.14 70)", ink: "oklch(30% 0.06 65)" },
  { from: "oklch(90% 0.06 35)", to: "oklch(82% 0.10 30)", accent: "oklch(72% 0.13 32)", ink: "oklch(30% 0.06 32)" },
  { from: "oklch(91% 0.05 230)", to: "oklch(83% 0.08 225)", accent: "oklch(66% 0.11 228)", ink: "oklch(30% 0.05 232)" },
  { from: "oklch(89% 0.05 145)", to: "oklch(82% 0.08 135)", accent: "oklch(60% 0.10 140)", ink: "oklch(28% 0.05 140)" },
  { from: "oklch(91% 0.06 95)", to: "oklch(84% 0.10 85)", accent: "oklch(76% 0.14 88)", ink: "oklch(30% 0.05 80)" },
];

// A script glyph that hints at the course language — literary, not a flag.
const LANGUAGE_GLYPH: Record<string, string> = {
  chinese: "中",
  mandarin: "中",
  cantonese: "粵",
  english: "A",
  japanese: "あ",
  korean: "한",
  spanish: "Es",
  french: "Fr",
  german: "De",
};

function seedHash(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return h;
}

/**
 * Deterministic per-course cover: a warm brand-family gradient with a single
 * language script glyph and a soft decorative arc. Stable per course id, and
 * unmistakably intentional (no more "broken image" reading).
 */
export function CourseIllustration({
  seed,
  language,
  className,
}: CourseIllustrationProps) {
  const hash = seedHash(seed);
  const palette = PALETTES[hash % PALETTES.length];
  const glyph =
    LANGUAGE_GLYPH[language.trim().toLowerCase()] ??
    (language.trim().slice(0, 1).toUpperCase() || "·");
  // Derive the gradient id from the unique course seed (a UUID), not the hash
  // bucket — SVG <defs> ids share a flat document namespace, so two courses
  // colliding on `hash` would otherwise share (and cross-wire) one gradient.
  const gradId = `cover-${seed.replace(/[^a-z0-9]/gi, "")}`;

  return (
    <div className={className} aria-hidden="true">
      <svg viewBox="0 0 120 120" preserveAspectRatio="xMidYMid slice" className="size-full">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={palette.from} />
            <stop offset="100%" stopColor={palette.to} />
          </linearGradient>
        </defs>
        <rect width="120" height="120" fill={`url(#${gradId})`} />
        {/* Soft decorative arcs for depth */}
        <circle cx="98" cy="24" r="30" fill={palette.accent} opacity="0.30" />
        <circle cx="20" cy="104" r="26" fill={palette.accent} opacity="0.22" />
        {/* Language glyph, set in the display serif */}
        <text
          x="50%"
          y="52%"
          dominantBaseline="middle"
          textAnchor="middle"
          fontFamily="var(--font-display), Georgia, serif"
          fontSize="54"
          fontWeight="600"
          fill={palette.ink}
          opacity="0.92"
        >
          {glyph}
        </text>
      </svg>
    </div>
  );
}
