import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import { QuestionRenderer, type RenderableQuestion } from "./question-renderer";
import { encodeAnswer, type AnswerDraft } from "./answer-encoding";

function renderWith(node: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {node}
    </NextIntlClientProvider>
  );
}

afterEach(() => cleanup());

describe("QuestionRenderer — ordering", () => {
  const question: RenderableQuestion = {
    id: "q1",
    type: "ordering",
    questionText: "Order these",
    options: ["x", "y", "z"],
  };

  it("emits a JSON id array in the new order after a move-down", () => {
    const onChange = vi.fn<(draft: AnswerDraft) => void>();
    renderWith(
      <QuestionRenderer
        question={question}
        draft={{ type: "ordering", order: ["x", "y", "z"] }}
        onChange={onChange}
      />
    );

    // Move the first item (x) down one slot.
    fireEvent.click(screen.getByRole("button", { name: "Move x down" }));

    expect(onChange).toHaveBeenCalledTimes(1);
    const draft = onChange.mock.calls[0][0];
    expect(draft).toEqual({ type: "ordering", order: ["y", "x", "z"] });
    // The wire shape the backend `grade_question` decodes is a JSON id array.
    expect(encodeAnswer(draft)).toBe(JSON.stringify(["y", "x", "z"]));
  });
});

describe("QuestionRenderer — multiple_choice", () => {
  it("emits the selected option key", () => {
    const onChange = vi.fn<(draft: AnswerDraft) => void>();
    renderWith(
      <QuestionRenderer
        question={{
          id: "q2",
          type: "multiple_choice",
          questionText: "Pick one",
          options: { a: "Alpha", b: "Beta" },
        }}
        draft={{ type: "multiple_choice", key: null }}
        onChange={onChange}
      />
    );

    fireEvent.click(screen.getByRole("radio", { name: /Beta/ }));

    expect(onChange).toHaveBeenCalledWith({
      type: "multiple_choice",
      key: "b",
    });
    expect(encodeAnswer(onChange.mock.calls[0][0])).toBe("b");
  });
});

describe("QuestionRenderer — matching", () => {
  it("emits a JSON left→right map when a pair is selected", () => {
    const onChange = vi.fn<(draft: AnswerDraft) => void>();
    renderWith(
      <QuestionRenderer
        question={{
          id: "q3",
          type: "matching",
          questionText: "Match them",
          options: {
            left: [{ id: "a", text: "Cat" }],
            right: [{ id: "1", text: "Chat" }],
          },
        }}
        draft={{ type: "matching", map: {} }}
        onChange={onChange}
      />
    );

    fireEvent.change(screen.getByLabelText("Cat"), {
      target: { value: "1" },
    });

    expect(onChange).toHaveBeenCalledWith({
      type: "matching",
      map: { a: "1" },
    });
    expect(encodeAnswer(onChange.mock.calls[0][0])).toBe(
      JSON.stringify({ a: "1" })
    );
  });
});
