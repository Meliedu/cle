import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, describe, expect, it, vi } from "vitest";

import messages from "../../../messages/en.json";
import type { PlacementItem } from "@/hooks/use-placement";
import { PlacementQuestion, isCompleteOrder } from "./placement-question";

afterEach(cleanup);

function choiceItem(overrides: Partial<PlacementItem> = {}): PlacementItem {
  return {
    id: "item-1",
    question_number: 1,
    section: "reading",
    response_format: "choice_4",
    option_letters: ["A", "B", "C", "D"],
    expected_seconds: 30,
    audio_playback: null,
    passage: null,
    stem: "女的是做什么的？",
    prompt: null,
    options: [
      { letter: "A", text: "老师" },
      { letter: "B", text: "医生" },
      { letter: "C", text: "学生" },
      { letter: "D", text: "护士" },
    ],
    ...overrides,
  };
}

function sequenceItem(): PlacementItem {
  return {
    ...choiceItem(),
    id: "item-seq",
    question_number: 25,
    response_format: "sequence",
    option_letters: ["A", "B", "C"],
    stem: "请把下面三个部分排列成语意连贯的一段话。",
    options: [
      { letter: "A", text: "敲了半天门也没人开" },
      { letter: "B", text: "后来才知道你在开会" },
      { letter: "C", text: "我刚才去你办公室找你" },
    ],
  };
}

function renderQuestion(item: PlacementItem, onChange = vi.fn(), value: string | null = null) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <PlacementQuestion item={item} value={value} onChange={onChange} />
    </NextIntlClientProvider>
  );
  return onChange;
}

describe("multiple-choice question", () => {
  it("shows the stem and every option", () => {
    renderQuestion(choiceItem());
    expect(screen.getByText("女的是做什么的？")).toBeTruthy();
    expect(screen.getByText("医生")).toBeTruthy();
    expect(screen.getAllByRole("radio")).toHaveLength(4);
  });

  it("reports the chosen letter, not the option text", () => {
    const onChange = renderQuestion(choiceItem());
    fireEvent.click(screen.getAllByRole("radio")[1]);
    expect(onChange).toHaveBeenCalledWith("B");
  });

  it("marks the current answer as checked", () => {
    renderQuestion(choiceItem(), vi.fn(), "C");
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios[2].checked).toBe(true);
  });

  it("never renders anything that could be a key", () => {
    // The safe payload has no key field at all, so this guards against a future
    // edit that adds one to the type and quietly renders it.
    const { container } = render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <PlacementQuestion item={choiceItem()} value={null} onChange={vi.fn()} />
      </NextIntlClientProvider>
    );
    const text = container.textContent ?? "";
    expect(text).not.toContain("correct");
    expect(text).not.toContain("Correct");
  });
});

function renderListening(props: { playCount?: number; audioAvailable?: boolean }) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <PlacementQuestion
        item={choiceItem({ section: "listening", audio_playback: 2 })}
        value={null}
        onChange={vi.fn()}
        playCount={props.playCount ?? 0}
        onPlay={vi.fn()}
        audioAvailable={props.audioAvailable ?? false}
      />
    </NextIntlClientProvider>
  );
}

describe("audio items", () => {
  it("offers a play control limited to the item's allowance", () => {
    renderListening({ audioAvailable: true });
    const playable = screen.getByRole("button", { name: /play audio/i }) as HTMLButtonElement;
    expect(playable.disabled).toBe(false);
    expect(screen.getByText(/2 of 2 plays left/i)).toBeTruthy();
  });

  it("disables playback once the allowance is spent", () => {
    renderListening({ audioAvailable: true, playCount: 2 });
    const spent = screen.getByRole("button", { name: /play audio/i }) as HTMLButtonElement;
    expect(spent.disabled).toBe(true);
  });

  it("offers no play control when no approved recording exists", () => {
    // A button that produces silence is worse than no button: mid-exam, a
    // learner would spend their own minutes deciding their audio is broken.
    renderListening({ audioAvailable: false });
    expect(screen.queryByRole("button", { name: /play audio/i })).toBeNull();
  });

  it("says a proctor reads the script instead", () => {
    renderListening({ audioAvailable: false });
    expect(screen.getByText(/read aloud 2 times by the person supervising/i)).toBeTruthy();
  });

  it("shows no audio affordance at all on a reading item", () => {
    renderQuestion(choiceItem());
    expect(screen.queryByRole("button", { name: /play audio/i })).toBeNull();
    expect(screen.queryByText(/read aloud/i)).toBeNull();
  });
});

describe("ordering question", () => {
  it("does not use radios, because ordering is not a single choice", () => {
    renderQuestion(sequenceItem());
    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(screen.getAllByRole("combobox")).toHaveLength(3);
  });

  it("reports a partial order so the learner does not lose it", () => {
    // The parent keeps this on screen but does not send it: a partial order is
    // not a legal response. Reporting nothing here would discard the first
    // choice as soon as the learner made the second.
    const onChange = renderQuestion(sequenceItem());
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "C" },
    });
    expect(onChange).toHaveBeenLastCalledWith("C--");
    expect(isCompleteOrder("C--", 3)).toBe(false);
  });

  it("keeps a partial order when the item is re-rendered with it", () => {
    // Paging away and back hands the same partial value straight back; the
    // positions already chosen must still be selected.
    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <PlacementQuestion item={sequenceItem()} value="C-A-" onChange={vi.fn()} />
      </NextIntlClientProvider>
    );
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    expect(selects[0].value).toBe("C");
    expect(selects[1].value).toBe("A");
    expect(selects[2].value).toBe("");
  });

  it("reports the full order once all three positions are set", () => {
    const onChange = vi.fn();
    const item = sequenceItem();
    const { rerender } = render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <PlacementQuestion item={item} value={null} onChange={onChange} />
      </NextIntlClientProvider>
    );

    // Drive it the way the parent does: each change feeds the new value back.
    let current: string | null = null;
    const set = (index: number, letter: string) => {
      const selects = screen.getAllByRole("combobox");
      fireEvent.change(selects[index], { target: { value: letter } });
      current = onChange.mock.calls.at(-1)?.[0] ?? current;
      rerender(
        <NextIntlClientProvider locale="en" messages={messages}>
          <PlacementQuestion item={item} value={current} onChange={onChange} />
        </NextIntlClientProvider>
      );
    };

    set(0, "C");
    set(1, "A");
    set(2, "B");

    expect(onChange).toHaveBeenLastCalledWith("C-A-B");
  });

  it("prevents the same fragment being used twice", () => {
    render(
      <NextIntlClientProvider locale="en" messages={messages}>
        <PlacementQuestion item={sequenceItem()} value={"C--"} onChange={vi.fn()} />
      </NextIntlClientProvider>
    );
    const selects = screen.getAllByRole("combobox") as HTMLSelectElement[];
    const secondSlotC = Array.from(selects[1].options).find((o) => o.value === "C");
    expect(secondSlotC?.disabled).toBe(true);
  });

  it("labels each position for assistive tech", () => {
    renderQuestion(sequenceItem());
    expect(screen.getByLabelText("Position 1")).toBeTruthy();
    expect(screen.getByLabelText("Position 3")).toBeTruthy();
  });
});

describe("passage rendering", () => {
  it("keeps the speaker turns of a dialogue on separate lines", () => {
    const item = choiceItem({
      passage: "男：你是学生吗？\n女：不是，我是医生。",
    });
    renderQuestion(item);
    expect(screen.getByText("男：你是学生吗？")).toBeTruthy();
    expect(screen.getByText("女：不是，我是医生。")).toBeTruthy();
  });

  it("renders the cloze instruction when the item has one", () => {
    renderQuestion(
      choiceItem({
        stem: null,
        passage: "如果没有明确的目标……",
        prompt: "请选择最合适的一项填入第（17）空。",
      })
    );
    expect(
      screen.getByText("请选择最合适的一项填入第（17）空。")
    ).toBeTruthy();
  });
});
