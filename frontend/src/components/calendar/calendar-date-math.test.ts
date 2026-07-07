import { describe, expect, it } from "vitest";

import {
  addDays,
  addMonths,
  addWeeks,
  buildMonthMatrix,
  buildWeekDays,
  isSameDay,
  isSameMonth,
  monthRange,
  startOfWeek,
  toIsoDate,
  weekRange,
} from "./calendar-date-math";

describe("toIsoDate", () => {
  it("formats a local calendar day as yyyy-mm-dd with zero padding", () => {
    expect(toIsoDate(new Date(2026, 5, 3))).toBe("2026-06-03");
    expect(toIsoDate(new Date(2026, 11, 25))).toBe("2026-12-25");
  });
});

describe("startOfWeek", () => {
  it("returns the Monday of the week for any weekday", () => {
    // 2026-06-03 is a Wednesday → Monday is 2026-06-01.
    expect(toIsoDate(startOfWeek(new Date(2026, 5, 3)))).toBe("2026-06-01");
    // A Monday maps to itself.
    expect(toIsoDate(startOfWeek(new Date(2026, 5, 1)))).toBe("2026-06-01");
    // A Sunday maps back to the prior Monday.
    expect(toIsoDate(startOfWeek(new Date(2026, 5, 7)))).toBe("2026-06-01");
  });
});

describe("addMonths", () => {
  it("clamps to the last valid day of the target month", () => {
    // Jan 31 + 1 month → Feb 28 (2026 is not a leap year), not March.
    expect(toIsoDate(addMonths(new Date(2026, 0, 31), 1))).toBe("2026-02-28");
  });

  it("moves backwards with a negative delta", () => {
    expect(toIsoDate(addMonths(new Date(2026, 5, 15), -1))).toBe("2026-05-15");
  });

  it("crosses year boundaries", () => {
    expect(toIsoDate(addMonths(new Date(2026, 11, 10), 1))).toBe("2027-01-10");
  });
});

describe("addDays / addWeeks", () => {
  it("shifts by days and weeks without mutating the input", () => {
    const base = new Date(2026, 5, 1);
    expect(toIsoDate(addDays(base, 5))).toBe("2026-06-06");
    expect(toIsoDate(addWeeks(base, 2))).toBe("2026-06-15");
    // input untouched
    expect(toIsoDate(base)).toBe("2026-06-01");
  });
});

describe("isSameDay / isSameMonth", () => {
  it("compares calendar day irrespective of time of day", () => {
    expect(
      isSameDay(new Date(2026, 5, 3, 8, 30), new Date(2026, 5, 3, 21, 0))
    ).toBe(true);
    expect(isSameDay(new Date(2026, 5, 3), new Date(2026, 5, 4))).toBe(false);
  });

  it("detects same month/year", () => {
    expect(isSameMonth(new Date(2026, 5, 30), new Date(2026, 5, 1))).toBe(true);
    expect(isSameMonth(new Date(2026, 6, 1), new Date(2026, 5, 1))).toBe(false);
  });
});

describe("buildWeekDays", () => {
  it("returns 7 consecutive days starting Monday", () => {
    const days = buildWeekDays(new Date(2026, 5, 3));
    expect(days).toHaveLength(7);
    expect(toIsoDate(days[0])).toBe("2026-06-01"); // Monday
    expect(toIsoDate(days[6])).toBe("2026-06-07"); // Sunday
    expect(days[0].getDay()).toBe(1);
    for (let i = 1; i < days.length; i++) {
      expect(toIsoDate(days[i])).toBe(toIsoDate(addDays(days[i - 1], 1)));
    }
  });
});

describe("buildMonthMatrix", () => {
  it("emits whole Monday-start weeks covering the entire month", () => {
    const anchor = new Date(2026, 1, 15); // February 2026
    const matrix = buildMonthMatrix(anchor);

    // Every row has exactly 7 days.
    for (const week of matrix) {
      expect(week).toHaveLength(7);
      expect(week[0].getDay()).toBe(1); // starts on Monday
    }

    const flat = matrix.flat();
    // First cell is on/before the 1st; last cell on/after the last of month.
    expect(flat[0].getTime()).toBeLessThanOrEqual(
      new Date(2026, 1, 1).getTime()
    );
    expect(flat[flat.length - 1].getTime()).toBeGreaterThanOrEqual(
      new Date(2026, 1, 28).getTime()
    );

    // Contains both the 1st and the 28th of the anchor month.
    expect(flat.some((d) => isSameDay(d, new Date(2026, 1, 1)))).toBe(true);
    expect(flat.some((d) => isSameDay(d, new Date(2026, 1, 28)))).toBe(true);

    // Cells are strictly consecutive days.
    for (let i = 1; i < flat.length; i++) {
      expect(toIsoDate(flat[i])).toBe(toIsoDate(addDays(flat[i - 1], 1)));
    }
  });

  it("produces a whole number of weeks (length divisible by 7)", () => {
    for (const month of [0, 1, 5, 7, 11]) {
      const flat = buildMonthMatrix(new Date(2026, month, 10)).flat();
      expect(flat.length % 7).toBe(0);
    }
  });

  it("starts the visible grid on the Monday before June 1 2026", () => {
    // June 1 2026 is a Monday, so the grid starts exactly on June 1.
    const matrix = buildMonthMatrix(new Date(2026, 5, 10));
    expect(toIsoDate(matrix[0][0])).toBe("2026-06-01");
  });
});

describe("monthRange / weekRange", () => {
  it("spans the visible month matrix as a half-open [from, to) window", () => {
    const anchor = new Date(2026, 5, 10);
    const matrix = buildMonthMatrix(anchor);
    const { from, to } = monthRange(anchor);
    expect(from).toBe(toIsoDate(matrix[0][0]));
    const lastWeek = matrix[matrix.length - 1];
    expect(to).toBe(toIsoDate(addDays(lastWeek[6], 1)));
  });

  it("spans exactly seven days for a week window", () => {
    const anchor = new Date(2026, 5, 3);
    const { from, to } = weekRange(anchor);
    expect(from).toBe("2026-06-01");
    expect(to).toBe("2026-06-08"); // exclusive end = Monday + 7
  });
});
