// Decorative honeycomb cluster used as the brand pane illustration on
// /sign-in /sign-up etc. Reuses the visual language of CourseIllustration
// (oklch warm tones, flat shapes, no gradients) so the auth surface feels
// part of the same system as the dashboard.

interface HoneycombMarkProps {
  readonly className?: string;
}

const HEX = "M30 0 L60 17.32 L60 51.96 L30 69.28 L0 51.96 L0 17.32 Z";

interface Cell {
  readonly x: number;
  readonly y: number;
  readonly fill: string;
  readonly opacity: number;
  readonly stroke?: string;
  readonly delay: number;
}

const CELLS: readonly Cell[] = [
  { x: 80, y: 60, fill: "oklch(88% 0.08 80)", opacity: 0.95, delay: 0 },
  { x: 140, y: 95, fill: "oklch(78% 0.14 80)", opacity: 0.9, delay: 80 },
  { x: 200, y: 60, fill: "oklch(70% 0.16 80)", opacity: 1, delay: 160 },
  { x: 110, y: 140, fill: "oklch(93% 0.04 75)", opacity: 1, stroke: "oklch(78% 0.08 75)", delay: 220 },
  { x: 170, y: 175, fill: "oklch(88% 0.07 35)", opacity: 0.85, delay: 320 },
  { x: 230, y: 140, fill: "oklch(95% 0.03 230)", opacity: 1, stroke: "oklch(70% 0.08 230)", delay: 380 },
  { x: 50, y: 220, fill: "oklch(80% 0.06 65)", opacity: 0.9, delay: 460 },
  { x: 110, y: 255, fill: "oklch(70% 0.13 35)", opacity: 0.85, delay: 540 },
  { x: 200, y: 255, fill: "oklch(60% 0.12 230)", opacity: 0.95, delay: 620 },
  { x: 260, y: 220, fill: "oklch(88% 0.05 65)", opacity: 0.9, delay: 700 },
];

export function HoneycombMark({ className }: HoneycombMarkProps) {
  return (
    <svg
      viewBox="0 0 320 360"
      role="presentation"
      aria-hidden="true"
      className={className}
    >
      <defs>
        <filter id="honeycomb-blur" x="-10%" y="-10%" width="120%" height="120%">
          <feGaussianBlur stdDeviation="14" />
        </filter>
      </defs>

      {/* Soft warm halo behind the cluster */}
      <ellipse
        cx="160"
        cy="180"
        rx="140"
        ry="120"
        fill="oklch(96% 0.04 75)"
        filter="url(#honeycomb-blur)"
        opacity="0.85"
      />

      {/* Cluster */}
      <g style={{ transformOrigin: "160px 180px" }}>
        {CELLS.map((cell, index) => (
          <g
            key={index}
            transform={`translate(${cell.x} ${cell.y})`}
            style={{
              transformOrigin: "30px 35px",
              transform: "scale(0)",
              opacity: 0,
              animation: `auth-honeycomb-pop 700ms var(--ease-spring, cubic-bezier(0.34, 1.56, 0.64, 1)) forwards`,
              animationDelay: `${cell.delay}ms`,
            }}
          >
            <path
              d={HEX}
              fill={cell.fill}
              opacity={cell.opacity}
              stroke={cell.stroke}
              strokeWidth={cell.stroke ? 1.5 : 0}
              strokeLinejoin="round"
            />
          </g>
        ))}
      </g>

      <style>{`
        @keyframes auth-honeycomb-pop {
          to {
            transform: scale(1);
            opacity: 1;
          }
        }
        @media (prefers-reduced-motion: reduce) {
          [style*="auth-honeycomb-pop"] {
            animation: none !important;
            transform: scale(1) !important;
            opacity: 1 !important;
          }
        }
      `}</style>
    </svg>
  );
}
