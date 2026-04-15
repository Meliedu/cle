import { useEffect, useRef, useState } from "react";

/**
 * Wall-clock countdown anchored to the server's reported `elapsedSeconds`.
 *
 * Both host and student consume the same `/state` poll, so if both sides run
 * this hook they will stay in sync within ~ one network round-trip. The
 * anchor is recomputed once per question (or on large drift) — NOT on every
 * poll — so the local ticker reads smoothly instead of jumping 1–2s each
 * time a new poll lands.
 *
 * Returns whole seconds remaining (ceil'd), clamped to [0, timeLimit].
 */
export function useLiveTimer(
  questionIndex: number | null | undefined,
  timeLimit: number,
  elapsedSeconds: number
): number {
  const anchorRef = useRef<{ index: number; anchorMs: number }>({
    index: -1,
    anchorMs: 0,
  });
  const [now, setNow] = useState<number>(() => Date.now());

  /* Re-anchor when a new question arrives, or when the server's reported
   * elapsed differs from ours by >1s (indicates a backend restart or clock
   * skew — trust the server over our local tick). */
  useEffect(() => {
    if (questionIndex == null || questionIndex < 0) return;
    const desiredAnchor = Date.now() - elapsedSeconds * 1000;
    const drift = Math.abs(anchorRef.current.anchorMs - desiredAnchor);
    if (
      anchorRef.current.index !== questionIndex ||
      drift > 1000
    ) {
      anchorRef.current = { index: questionIndex, anchorMs: desiredAnchor };
    }
  }, [questionIndex, elapsedSeconds]);

  /* Re-render 4×/s so the displayed countdown is smooth. Interval is gated
   * on having an active question so we don't spin while in the lobby. */
  useEffect(() => {
    if (questionIndex == null || questionIndex < 0) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [questionIndex]);

  if (questionIndex == null || questionIndex < 0) return 0;
  const elapsedLocal = (now - anchorRef.current.anchorMs) / 1000;
  const remaining = Math.ceil(timeLimit - elapsedLocal);
  return Math.max(0, Math.min(timeLimit, remaining));
}
