/**
 * Shared option palette for live-quiz surfaces. Kahoot-style high-contrast
 * colors that stay legible in both light and dark modes, applied positionally
 * so true_false (2 opts) and MCQ (4 opts) both look intentional.
 */
export const OPTION_BUTTON_STYLES: readonly string[] = [
  "bg-[oklch(60%_0.22_25)] hover:bg-[oklch(55%_0.22_25)] text-white",
  "bg-[oklch(55%_0.22_250)] hover:bg-[oklch(50%_0.22_250)] text-white",
  "bg-[oklch(68%_0.17_75)] hover:bg-[oklch(63%_0.17_75)] text-[oklch(18%_0_0)]",
  "bg-[oklch(60%_0.17_155)] hover:bg-[oklch(55%_0.17_155)] text-white",
];

export const OPTION_BAR_COLORS: readonly string[] = [
  "oklch(60% 0.22 25)",
  "oklch(55% 0.22 250)",
  "oklch(68% 0.17 75)",
  "oklch(60% 0.17 155)",
];

export const OPTION_ICONS: readonly string[] = ["◆", "■", "●", "▲"];
