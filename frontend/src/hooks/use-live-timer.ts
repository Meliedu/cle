import { useEffect, useState } from "react";

interface Anchor {
  readonly index: number;
  readonly anchorMs: number;
}

const NO_ANCHOR: Anchor = { index: -1, anchorMs: 0 };

/**
 * Wall-clock countdown anchored to the server's reported `elapsedSeconds`.
 *
 * Both host and student consume the same `/state` poll, so if both sides run
 * this hook they will stay in sync within ~ one network round-trip. The
 * anchor is recomputed once per question (or on large drift) — NOT on every
 * poll — so the local ticker reads smoothly instead of jumping 1–2s each
 * time a new poll lands.
 *
 * The anchor lives in state rather than a ref: render derives the displayed
 * value from it, and reading a ref during render is neither pure nor safe
 * under concurrent rendering (a ref mutated by an effect can be torn between
 * two renders of the same commit). State makes the whole render a pure
 * function of its inputs.
 *
 * Returns whole seconds remaining (ceil'd), clamped to [0, timeLimit].
 */
export function useLiveTimer(
  questionIndex: number | null | undefined,
  timeLimit: number,
  elapsedSeconds: number
): number {
  const [anchor, setAnchor] = useState<Anchor>(NO_ANCHOR);
  const [now, setNow] = useState<number>(() => Date.now());

  /* Re-anchor when a new question arrives, or when the server's reported
   * elapsed differs from ours by >1s (indicates a backend restart or clock
   * skew — trust the server over our local tick). */
  useEffect(() => {
    if (questionIndex == null || questionIndex < 0) return;
    const desiredAnchor = Date.now() - elapsedSeconds * 1000;
    setAnchor((prev) =>
      prev.index !== questionIndex ||
      Math.abs(prev.anchorMs - desiredAnchor) > 1000
        ? { index: questionIndex, anchorMs: desiredAnchor }
        : prev
    );
  }, [questionIndex, elapsedSeconds]);

  /* Re-render 4×/s so the displayed countdown is smooth. Interval is gated
   * on having an active question so we don't spin while in the lobby. */
  useEffect(() => {
    if (questionIndex == null || questionIndex < 0) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [questionIndex]);

  if (questionIndex == null || questionIndex < 0) return 0;

  /* On the first render after a new question arrives, `anchor` still holds
   * the previous question's value (the sync effect above hasn't run yet:
   * effects fire post-commit). Using the stale anchor returns 0 for one
   * frame, which briefly flips the host panel into the "time up / reveal"
   * state and leaks the correct answer in green. Derive a fresh anchor
   * locally instead.
   *
   * The fallback anchors off the `now` state rather than a fresh `Date.now()`
   * so render stays pure, and it is the more accurate of the two, since
   * `now - elapsedSeconds * 1000` makes `elapsedLocal` collapse to exactly
   * `elapsedSeconds`. The first frame therefore shows precisely the server's
   * reported remaining time. */
  const anchorMs =
    anchor.index === questionIndex
      ? anchor.anchorMs
      : now - elapsedSeconds * 1000;
  const elapsedLocal = (now - anchorMs) / 1000;
  const remaining = Math.ceil(timeLimit - elapsedLocal);
  return Math.max(0, Math.min(timeLimit, remaining));
}
