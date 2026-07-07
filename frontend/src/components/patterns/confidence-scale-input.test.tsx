import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfidenceScaleInput } from "./confidence-scale-input";
import type { ConfidenceScale } from "@/lib/pilot-config";

const SCALE: ConfidenceScale = {
  min: -2,
  max: 2,
  labels: {
    "-2": "No idea",
    "-1": "Shaky",
    "0": "Neutral",
    "1": "Mostly",
    "2": "Confident",
  },
};

afterEach(cleanup);

describe("ConfidenceScaleInput", () => {
  it("renders one radio per −2..+2 point with its config label", () => {
    const { container, getByText } = render(
      <ConfidenceScaleInput scale={SCALE} value={null} onChange={vi.fn()} />
    );

    const radios = container.querySelectorAll('input[type="radio"]');
    expect(radios.length).toBe(5);

    // All five config labels render in scale order.
    for (const label of Object.values(SCALE.labels)) {
      expect(getByText(label)).toBeTruthy();
    }
    // Nothing is selected when value is null.
    expect(container.querySelector('input[type="radio"]:checked')).toBeNull();
  });

  it("falls back to the numeric value when a label is missing", () => {
    const sparse: ConfidenceScale = { min: -1, max: 1, labels: { "0": "Mid" } };
    const { getByText } = render(
      <ConfidenceScaleInput scale={sparse} value={null} onChange={vi.fn()} />
    );
    expect(getByText("-1")).toBeTruthy();
    expect(getByText("Mid")).toBeTruthy();
    expect(getByText("1")).toBeTruthy();
  });

  it("fires onChange with the numeric scale point when a card is clicked", () => {
    const onChange = vi.fn();
    const { getByText } = render(
      <ConfidenceScaleInput scale={SCALE} value={null} onChange={onChange} />
    );

    fireEvent.click(getByText("Confident"));
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(2);

    fireEvent.click(getByText("No idea"));
    expect(onChange).toHaveBeenLastCalledWith(-2);
  });

  it("reflects the controlled value as the checked radio", () => {
    const { container } = render(
      <ConfidenceScaleInput scale={SCALE} value={0} onChange={vi.fn()} />
    );
    const checked = container.querySelectorAll<HTMLInputElement>(
      'input[type="radio"]:checked'
    );
    expect(checked.length).toBe(1);
  });

  it("disables every radio when disabled", () => {
    const { container } = render(
      <ConfidenceScaleInput scale={SCALE} value={null} onChange={vi.fn()} disabled />
    );
    const radios = container.querySelectorAll<HTMLInputElement>(
      'input[type="radio"]'
    );
    for (const radio of radios) {
      expect(radio.disabled).toBe(true);
    }
  });

  it("keeps distinct radio-group names for two instances by default", () => {
    const { container } = render(
      <>
        <ConfidenceScaleInput scale={SCALE} value={null} onChange={vi.fn()} />
        <ConfidenceScaleInput scale={SCALE} value={null} onChange={vi.fn()} />
      </>
    );
    const names = new Set(
      Array.from(
        container.querySelectorAll<HTMLInputElement>('input[type="radio"]')
      ).map((r) => r.name)
    );
    // Two independent generated group names.
    expect(names.size).toBe(2);
  });
});
