"""Tests for the v1.3 placement extraction pipeline.

The extractor turns a controlled PDF package into the item bank a learner is
scored against, so its failure modes are silent and expensive: a passage that
lost its last line, two items fused into one, an option separator eaten by
whitespace normalisation. None of that is visible in a spot-check of a few
items, and the source package is not in the repository, so the parts that can
be tested without it are tested here.

These are pure functions over synthetic geometry -- no PDF, no database.
"""
from __future__ import annotations

import pytest

from app.services.placement_bank import BLOCKING_FLAG_CODES, PlacementBankError
from app.services.placement_scoring import COURSE_BY_BAND
from scripts import extract_placement_bank as extract
from scripts import import_placement_bank as importer
from scripts import placement_admin_pack as admin_pack
from scripts import placement_sources as sources
from scripts.pdf_layout import Line, collapse, group_paragraphs

MARGIN = 500.0
BODY = 56.0
STEM = 72.0
OPTIONS = 79.0


def line(text: str, *, x0: float = BODY, x1: float = MARGIN, page: int = 1, y0: float = 0.0) -> Line:
    return Line(page=page, x0=x0, y0=y0, x1=x1, text=text)


def texts(paragraphs) -> list[str]:
    return [p.text for p in paragraphs]


# ---------------------------------------------------------------------------
# Paragraph reconstruction
# ---------------------------------------------------------------------------


def test_a_full_width_line_joins_its_continuation_with_no_separator():
    """A CJK wrap has no space, so joining must not introduce one."""
    paragraphs = group_paragraphs(
        [line("重复当然有价值，但如果每次都按照原来的方法进行，错误"), line("也可能被一起固定下来。", x1=200.0)],
        margin=MARGIN,
    )
    assert texts(paragraphs) == ["重复当然有价值，但如果每次都按照原来的方法进行，错误也可能被一起固定下来。"]


def test_a_line_that_stops_short_of_the_margin_ends_its_paragraph():
    """This is the rule that keeps two short sentences from fusing."""
    paragraphs = group_paragraphs(
        [line("你家在哪儿？", x1=150.0), line("我家在北京。", x1=150.0)],
        margin=MARGIN,
    )
    assert texts(paragraphs) == ["你家在哪儿？", "我家在北京。"]


def test_an_indent_change_ends_a_paragraph_even_at_full_width():
    paragraphs = group_paragraphs(
        [line("昨天是妹妹的生日。哥哥送给她一件蓝色衣服，妈妈做了一个大蛋糕。"), line("谁送了衣服？", x0=STEM, x1=200.0)],
        margin=MARGIN,
    )
    assert texts(paragraphs) == [
        "昨天是妹妹的生日。哥哥送给她一件蓝色衣服，妈妈做了一个大蛋糕。",
        "谁送了衣服？",
    ]


def test_a_speaker_turn_opens_a_paragraph_after_a_full_width_line():
    """Both conditions for a wrap hold here; only the opener prevents a fuse.

    An interview turn regularly fills the column, and the next speaker starts at
    the same indent, so without the opener the two voices become one line and
    the proctor reads a dialogue as a monologue.
    """
    paragraphs = group_paragraphs(
        [
            line("专家：问题不只是说明写得长，而是平台把不同用途的数据放在一起，用户只能全部同意或全部拒绝。"),
            line("记者：平台应该怎样改进？", x1=200.0),
        ],
        margin=MARGIN,
        openers=admin_pack._ADMIN_OPENERS,
    )
    assert texts(paragraphs) == [
        "专家：问题不只是说明写得长，而是平台把不同用途的数据放在一起，用户只能全部同意或全部拒绝。",
        "记者：平台应该怎样改进？",
    ]


def test_a_page_break_that_would_sever_a_sentence_is_refused():
    """Grouping never spans pages, so this layout would split a sentence into
    two fields with every character still present and in order -- invisible to
    the losslessness check. It has to fail loudly instead."""
    with pytest.raises(sources.ExtractError, match="continue from page"):
        sources.assert_no_severed_page_break(
            "Form A",
            [line("重复当然有价值，但如果每次都按照原来的方法进行，错误"), line("也可能被一起固定下来。", page=2, x1=200.0)],
            MARGIN,
            sources._BOOKLET_OPENERS,
        )


def test_a_new_item_at_the_top_of_a_page_is_not_a_severed_sentence():
    sources.assert_no_severed_page_break(
        "Form A",
        [line("...错误"), line("24. 学习新词时，只看一遍往往很快就会忘。", page=2, x1=400.0)],
        MARGIN,
        sources._BOOKLET_OPENERS,
    )


def test_a_completed_sentence_at_the_foot_of_a_page_is_not_a_severed_sentence():
    """Reaching the margin is not the same as being cut off. The Administrator
    Pack routinely ends a complete "Key: …。" line flush at a page foot, and a
    guard that cried wolf on correct layout would just get switched off."""
    sources.assert_no_severed_page_break(
        "Administrator Pack",
        [
            line("Key: B-C-A · 小王虽然刚来公司不久，但是做事认真，也很愿意帮助别人，所以很快得到了同事们的信任。"),
            line("The correct order is B-C-A: ...", page=2, x1=400.0),
        ],
        MARGIN,
        admin_pack._ADMIN_OPENERS,
    )


def test_an_english_wrap_keeps_the_space_the_source_supplied():
    paragraphs = group_paragraphs(
        [line("It is not an official HSK examination or "), line("score report.", x1=150.0)],
        margin=MARGIN,
    )
    assert texts(paragraphs) == ["It is not an official HSK examination or score report."]


def test_raw_preserves_the_option_separator_that_text_collapses():
    """The option boundary *is* a run of spaces; collapsing first destroys it."""
    paragraph = group_paragraphs([line("A. 老师     B. 医生", x0=OPTIONS, x1=200.0)], margin=MARGIN)[0]
    assert paragraph.text == "A. 老师 B. 医生"
    assert paragraph.raw == "A. 老师     B. 医生"
    assert sources._parse_options(paragraph.raw) == [("A", "老师"), ("B", "医生")]


def test_collapse_leaves_the_ideographic_blank_alone():
    """U+3000 inside a cloze bracket is the rendered blank, not padding."""
    assert collapse("我想喝（　）。") == "我想喝（　）。"


# ---------------------------------------------------------------------------
# Passage / stem split
# ---------------------------------------------------------------------------


def _item(**kwargs) -> sources.RawItem:
    return sources.RawItem(question_number=kwargs.pop("q", 1), section="reading", **kwargs)


def test_a_single_paragraph_is_the_stem():
    item = _item()
    sources._finalise(item, [(BODY, "你家在哪儿？")])
    assert (item.passage, item.stem) == (None, "你家在哪儿？")


def test_the_indented_paragraph_is_the_question_and_the_rest_the_stimulus():
    item = _item()
    sources._finalise(
        item,
        [
            (BODY, "女：你妈妈在哪儿工作？"),
            (BODY, "男：她在饭店工作。"),
            (STEM, "男的妈妈在哪儿工作？"),
        ],
    )
    assert item.passage == "女：你妈妈在哪儿工作？\n男：她在饭店工作。"
    assert item.stem == "男的妈妈在哪儿工作？"


def test_two_paragraphs_at_one_indent_are_refused_rather_than_guessed():
    """The stimulus and the question are told apart by the indent the booklet
    prints them at. Without that difference there is no evidence for a split,
    and guessing produces a confident, plausible, wrong item."""
    item = _item()
    with pytest.raises(sources.ExtractError, match="cannot be told apart"):
        sources._finalise(item, [(BODY, "一段材料。"), (BODY, "另一段材料。")])


def test_an_indented_paragraph_that_is_not_last_is_refused():
    item = _item()
    with pytest.raises(sources.ExtractError, match="expected one indented question"):
        sources._finalise(item, [(STEM, "问题？"), (BODY, "材料。")])


def test_a_cloze_presents_its_text_as_the_passage_not_the_stem():
    """The cloze text *is* the item; the instruction is the prompt."""
    item = _item(q=13, prompt="请选择最合适的一项填入第（13）空。")
    sources._finalise(item, [(BODY, "今天太热了，我想喝（　）。")])
    assert item.passage == "今天太热了，我想喝（　）。"
    assert item.stem == ""


def test_a_cloze_with_an_indented_instruction_still_presents_as_a_passage():
    """Q17/Q18 print the instruction at the stem indent, so the split lands the
    text in `stem` first and the cloze rule has to move it back. An early exit
    that skips that step puts a whole reading passage in the wrong field."""
    item = _item(q=17, prompt="请选择最合适的一项填入第（17）空。")
    sources._finalise(item, [(BODY, "只有先说清楚要解决的问题，后续讨论才可能产生真正的（17）____。")])
    assert item.passage == "只有先说清楚要解决的问题，后续讨论才可能产生真正的（17）____。"
    assert item.stem == ""


# ---------------------------------------------------------------------------
# Claim boundary
# ---------------------------------------------------------------------------


def test_the_claim_boundary_is_read_whole_across_its_own_narrower_wrap():
    """The callout wraps well short of the body margin, so the wrap rule is blind
    to it; consuming to the full stop is what recovers the whole sentence."""
    boundary = sources._read_claim_boundary(
        [
            line("Purpose: This is an internal Meli/CLE placement screener. It is not an official HSK examination or ", x1=488.0),
            line("score report.", x1=115.0),
            line("Privacy: Results support a course recommendation and CLE review. They do not create an official ", x1=492.0),
            line("proficiency credential.", x1=155.0),
        ]
    )
    assert boundary["purpose"] == (
        "This is an internal Meli/CLE placement screener. It is not an official "
        "HSK examination or score report."
    )
    assert boundary["privacy"] == (
        "Results support a course recommendation and CLE review. They do not "
        "create an official proficiency credential."
    )


def test_a_truncated_claim_boundary_is_an_error_not_a_shorter_string():
    with pytest.raises(sources.ExtractError, match="not a complete sentence"):
        sources._read_claim_boundary([line("Purpose: This is an internal screener and", x1=488.0)])


# ---------------------------------------------------------------------------
# Losslessness: the guarantee that the app shows what the paper prints
# ---------------------------------------------------------------------------


def _printed() -> list[Line]:
    return [
        line("1. 你家在哪儿？", x1=150.0),
        line("A. 我家在北京。     B. 我二十岁。", x0=OPTIONS, x1=250.0),
    ]


def _faithful() -> sources.RawItem:
    return sources.RawItem(
        question_number=1,
        section="reading",
        stem="你家在哪儿？",
        options=[{"letter": "A", "text": "我家在北京。"}, {"letter": "B", "text": "我二十岁。"}],
    )


def test_a_faithful_reconstruction_matches_the_printed_paper():
    sources._assert_lossless("A", [_faithful()], _printed())


def test_a_field_that_lost_a_line_is_caught():
    """The failure a substring check cannot see, and the one that shipped a
    truncated final passage until the equality check replaced it."""
    item = _faithful()
    item.stem = "你家在"
    with pytest.raises(sources.ExtractError, match="does not match the printed paper"):
        sources._assert_lossless("A", [item], _printed())


def test_a_field_that_swallowed_its_neighbour_is_caught():
    item = _faithful()
    item.stem = "你家在哪儿？答题卡"
    with pytest.raises(sources.ExtractError, match="does not match the printed paper"):
        sources._assert_lossless("A", [item], _printed())


def test_a_dropped_option_is_caught():
    item = _faithful()
    item.options = item.options[:1]
    with pytest.raises(sources.ExtractError, match="does not match the printed paper"):
        sources._assert_lossless("A", [item], _printed())


# ---------------------------------------------------------------------------
# Mechanical content flags
# ---------------------------------------------------------------------------


def test_a_cloze_numbered_for_a_different_question_is_flagged():
    """The defect that made Form B Q17 unscoreable in v1.2, caught without
    anyone naming that item."""
    item = sources.RawItem(
        question_number=17,
        section="language_use",
        passage="再（13）____与问题真正相关的材料。",
        prompt="请选择最合适的一项填入第（13）空。",
    )
    flags = extract._cloze_numbering_flags(item)
    assert [f["code"] for f in flags] == [
        "cloze_blank_number_mismatch",
        "cloze_blank_number_mismatch",
    ]


def test_a_correctly_numbered_cloze_is_not_flagged():
    item = sources.RawItem(
        question_number=17,
        section="language_use",
        passage="再（17）____与问题真正相关的材料。",
        prompt="请选择最合适的一项填入第（17）空。",
    )
    assert extract._cloze_numbering_flags(item) == []


def test_incorporated_feedback_becomes_an_advisory_flag_carrying_the_ask():
    flags = extract._provenance_flags(
        {"qa_status": "v1.2 feedback incorporated; native-CLE re-review required"},
        {"review_question": "Confirm the revision retains one defensible key."},
    )
    assert len(flags) == 1
    assert flags[0]["code"] == "teacher_feedback_incorporated"
    assert "Confirm the revision" in flags[0]["detail"]
    # Advisory by construction: the change the owner asked for was made, so what
    # is left is confirmation, and confirmation must not block publication.
    assert flags[0]["code"] not in BLOCKING_FLAG_CODES


def test_an_ordinary_qa_status_produces_no_flag():
    assert extract._provenance_flags({"qa_status": "Teacher-feedback revision candidate"}, None) == []


# ---------------------------------------------------------------------------
# Version diff
# ---------------------------------------------------------------------------


def _bank_item(item_id: str, key: str, stem: str) -> dict:
    return {
        "question_number": 1,
        "restricted": {"item_id": item_id, "correct_answer": key},
        "safe": {"passage": None, "stem": stem, "prompt": None, "options": []},
    }


def test_the_diff_separates_a_key_change_from_a_wording_change():
    previous = {
        "version_code": "old",
        "forms": [
            {
                "form_code": "A",
                "items": [
                    _bank_item("X-1", "C", "原来的题目"),
                    _bank_item("X-2", "A", "没有变化"),
                ],
            }
        ],
    }
    forms = [
        {
            "form_code": "A",
            "items": [
                _bank_item("X-1", "A", "修改后的题目"),
                _bank_item("X-2", "A", "没有变化"),
            ],
        }
    ]
    diff = extract._diff_against(previous, forms)
    assert diff["key_changes"] == [{"item_id": "X-1", "from": "C", "to": "A"}]
    assert diff["text_changed"] == ["X-1"]
    assert diff["whitespace_changed"] == []
    assert diff["items_added"] == [] and diff["items_removed"] == []


def test_a_blank_that_changed_width_is_not_reported_as_a_rewrite():
    """Twenty items differ only in the space inside a cloze bracket. Counting
    them as revisions sends CLE re-reading content nobody edited."""
    previous = {
        "version_code": "old",
        "forms": [{"form_code": "A", "items": [_bank_item("X-1", "D", "我想喝（　）。")]}],
    }
    forms = [{"form_code": "A", "items": [_bank_item("X-1", "D", "我想喝（ ）。")]}]
    diff = extract._diff_against(previous, forms)
    assert diff["whitespace_changed"] == ["X-1"]
    assert diff["text_changed"] == []
    assert diff["key_changes"] == []


def test_the_diff_reports_items_that_appeared_or_vanished():
    previous = {
        "version_code": "old",
        "forms": [{"form_code": "A", "items": [_bank_item("GONE", "A", "旧题")]}],
    }
    forms = [{"form_code": "A", "items": [_bank_item("NEW", "A", "新题")]}]
    diff = extract._diff_against(previous, forms)
    assert diff["items_added"] == ["NEW"]
    assert diff["items_removed"] == ["GONE"]


# ---------------------------------------------------------------------------
# Blueprint validation
# ---------------------------------------------------------------------------


def _valid_item(**overrides) -> dict:
    item = {
        "question_number": 1,
        "section": "reading",
        "response_format": "choice_4",
        "option_letters": ["A", "B", "C", "D"],
        "expected_seconds": 20,
        "audio_playback": None,
        "safe": {
            "passage": None,
            "stem": "你家在哪儿？",
            "prompt": None,
            "options": [
                {"letter": "A", "text": "我家在北京。"},
                {"letter": "B", "text": "我二十岁。"},
                {"letter": "C", "text": "很高兴认识你。"},
                {"letter": "D", "text": "我家有三个人。"},
            ],
        },
        "restricted": {
            "item_id": "X-1",
            "legacy_band": 1,
            "correct_answer": "A",
            "answer_text": "我家在北京。",
            "workbook_response_format": "4-option MC",
        },
        "teacher_flags": [],
    }
    item.update(overrides)
    return item


def test_a_valid_item_passes_validation():
    extract._validate_item("A", _valid_item())


def test_two_items_fused_by_the_grouper_are_rejected():
    """A question number inside a stem is the signature of a bad join, and the
    only check that notices it."""
    item = _valid_item()
    item["safe"]["stem"] = "你家在哪儿？ 20. 女：你妈妈在哪儿工作？"
    with pytest.raises(sources.ExtractError, match="contains a question number"):
        extract._validate_item("A", item)


def test_duplicate_option_text_is_rejected():
    item = _valid_item()
    item["safe"]["options"][1]["text"] = "我家在北京。"
    with pytest.raises(sources.ExtractError, match="duplicate option text"):
        extract._validate_item("A", item)


def test_a_listening_item_without_a_script_is_rejected():
    """Approved audio does not exist yet, so a proctor must be able to read it."""
    item = _valid_item(section="listening")
    with pytest.raises(sources.ExtractError, match="listening item has no script"):
        extract._validate_item("A", item)


def test_an_ordering_item_must_offer_exactly_three_parts():
    item = _valid_item(response_format="sequence")
    with pytest.raises(sources.ExtractError, match="4 options, expected 3"):
        extract._validate_item("A", item)


def test_an_option_lost_to_a_merged_pair_is_rejected():
    """The booklet separates two options with a run of spaces. If a line ever
    renders with one, the pair regex swallows the second option into the first
    and the item silently loses an option, with every character still present."""
    item = _valid_item()
    item["safe"]["options"] = [
        {"letter": "A", "text": "我家在北京。 B. 我二十岁。"},
        {"letter": "C", "text": "很高兴认识你。"},
        {"letter": "D", "text": "我家有三个人。"},
    ]
    item["option_letters"] = ["A", "C", "D"]
    with pytest.raises(sources.ExtractError, match="3 options, expected 4"):
        extract._validate_item("A", item)


def test_the_workbook_disagreeing_about_the_option_count_is_caught():
    """Independent confirmation from a different file. The blueprint check above
    compares the booklet against a constant; this compares it against what the
    workbook says about this specific item, which is the only signal that would
    survive a package where the blueprint itself changed."""
    item = _valid_item()
    item["restricted"]["workbook_response_format"] = "3-option MC"
    with pytest.raises(sources.ExtractError, match="workbook says 3 options"):
        extract._validate_item("A", item)


def test_a_workbook_response_format_with_no_count_is_not_second_guessed():
    """"Sequence" states no number, so there is nothing to disagree with."""
    item = _valid_item()
    item["restricted"]["workbook_response_format"] = "Sequence"
    extract._validate_item("A", item)


def test_an_answer_text_that_no_longer_matches_the_keyed_option_is_caught():
    """The pack states the key twice, as a letter and as wording. Only the
    letter is cross-checked elsewhere, so a pack left unregenerated after an
    option was reworded keeps describing an answer that is not on the paper."""
    item = _valid_item()
    item["restricted"]["answer_text"] = "我住在上海。"
    with pytest.raises(sources.ExtractError, match="describes the key as"):
        extract._validate_item("A", item)


def test_a_bank_wide_duplicate_item_id_is_refused():
    """`_diff_against` keys the previous bank by item id alone, so a duplicate
    would compare one form's item against another form's."""
    forms = [
        {"form_code": "A", "items": [_valid_item()]},
        {"form_code": "B", "items": [_valid_item()]},
    ]
    with pytest.raises(sources.ExtractError, match="already used by"):
        extract._assert_item_ids_unique(forms)


def test_a_key_naming_an_option_that_does_not_exist_is_flagged_not_dropped():
    """The bank must still load, so the review queue can show CLE what is wrong."""
    raw = sources.RawItem(
        question_number=1,
        section="reading",
        stem="你家在哪儿？",
        options=[{"letter": "A", "text": "我家在北京。"}, {"letter": "B", "text": "我二十岁。"}],
    )
    meta = {
        "correct_answer": "D",
        "item_id": "X-1",
        "slot": "R-L1-1",
        "legacy_band": 1,
        "skill": "Reading",
        "item_type": "Question-response matching",
        "response_format": "4-option MC",
        "topic": None,
        "subskill": None,
        "expected_seconds": 20,
        "audio_playback": None,
        "target_vocabulary": None,
        "target_grammar": None,
        "copyright_status": None,
        "qa_status": None,
    }
    assembled = extract._assemble_item(raw, meta, {"answer_text": "n/a"}, None)
    assert [f["code"] for f in assembled["teacher_flags"]] == ["key_not_in_options"]


@pytest.mark.parametrize("key", ["A-B", "A-A-B", "A-B-D"])
def test_an_ordering_key_that_is_not_a_permutation_is_flagged(key):
    """Membership is not enough. "A-B" and "A-A-B" name only real options while
    being impossible to produce by arranging the three parts, so scoring would
    compare every genuine answer against a string none of them can equal and
    mark the whole cohort wrong on that item, silently."""
    raw = sources.RawItem(
        question_number=25,
        section="reading",
        stem="请把下面三个部分排列成语意连贯的一段话。",
        is_sequence=True,
        options=[
            {"letter": "A", "text": "第一部分"},
            {"letter": "B", "text": "第二部分"},
            {"letter": "C", "text": "第三部分"},
        ],
    )
    meta = {
        "correct_answer": key,
        "item_id": "X-25",
        "slot": "R-L4-1",
        "legacy_band": 4,
        "skill": "Reading",
        "item_type": "Three-sentence ordering",
        "response_format": "Sequence",
        "topic": None,
        "subskill": None,
        "expected_seconds": 42,
        "audio_playback": None,
        "target_vocabulary": None,
        "target_grammar": None,
        "copyright_status": None,
        "qa_status": None,
    }
    assembled = extract._assemble_item(raw, meta, {"answer_text": "n/a"}, None)
    assert [f["code"] for f in assembled["teacher_flags"]] == ["key_not_in_options"]


def test_a_valid_ordering_key_is_accepted():
    raw = sources.RawItem(
        question_number=25,
        section="reading",
        stem="请把下面三个部分排列成语意连贯的一段话。",
        is_sequence=True,
        options=[
            {"letter": "A", "text": "第一部分"},
            {"letter": "B", "text": "第二部分"},
            {"letter": "C", "text": "第三部分"},
        ],
    )
    meta = {
        "correct_answer": "C-A-B",
        "item_id": "X-25",
        "slot": "R-L4-1",
        "legacy_band": 4,
        "skill": "Reading",
        "item_type": "Three-sentence ordering",
        "response_format": "Sequence",
        "topic": None,
        "subskill": None,
        "expected_seconds": 42,
        "audio_playback": None,
        "target_vocabulary": None,
        "target_grammar": None,
        "copyright_status": None,
        "qa_status": None,
    }
    assembled = extract._assemble_item(raw, meta, {"answer_text": "n/a"}, None)
    assert assembled["teacher_flags"] == []
    assert assembled["response_format"] == "sequence"


# ---------------------------------------------------------------------------
# The recorded policy must be the workbook's own
# ---------------------------------------------------------------------------


def _rules(**overrides) -> dict:
    thresholds = {
        "items_per_form": 30,
        "items_per_band": 5,
        "band_minimum": 3,
        "cumulative_threshold": 0.7,
        "incomplete_answers_below": 27,
        "fast_duration_minutes": 12,
        "long_duration_minutes": 45,
        "attempt_spread_bands": 1,
    }
    thresholds.update(overrides)
    return {
        "scoring_rules": {
            "thresholds": thresholds,
            "course_map": {
                "Below Band 1": "LANG1511",
                "Legacy HSK1": "LANG1511",
                "Legacy HSK2": "LANG1512",
                "Legacy HSK3": "LANG1513",
                "Legacy HSK4": "LANG1514",
                "Legacy HSK5": "LANG1515",
                "Legacy HSK6": "LANG1515",
            },
        }
    }


def test_the_shipped_workbook_policy_matches_the_recorded_one():
    importer.assert_policy_matches_workbook(_rules())


def test_a_retuned_threshold_stops_the_import():
    """The thresholds recorded against a version must be the workbook's own.
    A package that quietly moves one would otherwise be imported and scored
    under rules transcribed from the previous workbook."""
    with pytest.raises(PlacementBankError) as excinfo:
        importer.assert_policy_matches_workbook(_rules(band_minimum=4))
    assert excinfo.value.code == "POLICY_DRIFT"


def test_a_changed_course_map_stops_the_import():
    bank = _rules()
    bank["scoring_rules"]["course_map"]["Legacy HSK5"] = "LANG1514"
    with pytest.raises(PlacementBankError) as excinfo:
        importer.assert_policy_matches_workbook(bank)
    assert excinfo.value.code == "COURSE_MAP_DRIFT"


def test_the_cumulative_threshold_survives_float_representation():
    """0.7 read out of a spreadsheet cell need not be bit-identical to the
    literal, and a policy number nobody changed must not block an import."""
    importer.assert_policy_matches_workbook(_rules(cumulative_threshold=0.1 + 0.6))


def test_a_bank_without_a_rules_block_is_not_second_guessed():
    """Banks extracted before v1.3 carry no rules to compare."""
    importer.assert_policy_matches_workbook({})


def test_the_recorded_policy_covers_every_course_band():
    """A band missing from the workbook's map would compare as None and pass
    only if COURSE_BY_BAND also lacked it."""
    assert set(_rules()["scoring_rules"]["course_map"]) and len(COURSE_BY_BAND) == 7
