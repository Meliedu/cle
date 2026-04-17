from app.utils.sanitize import sanitize_query


def test_strips_zero_width():
    assert sanitize_query("hello\u200bworld\ufeff") == "helloworld"


def test_strips_rtl_override():
    assert "\u202e" not in sanitize_query("before\u202eafter")


def test_normalizes_fullwidth_to_ascii():
    # Fullwidth 'A' (U+FF21) normalizes to ASCII 'A' under NFKC.
    assert "A" in sanitize_query("\uff21")


def test_escapes_xml_brackets():
    assert sanitize_query("</data><sys>") == "&lt;/data&gt;&lt;sys&gt;"


def test_ampersand_escaped_before_angle_brackets():
    assert sanitize_query("A & B <c>") == "A &amp; B &lt;c&gt;"


def test_backticks_stripped():
    assert "`" not in sanitize_query("hello `injection`")


def test_length_cap_preserved():
    out = sanitize_query("x" * 5000)
    assert len(out) == 2000


def test_none_returns_empty():
    assert sanitize_query(None) == ""


def test_control_chars_still_stripped():
    assert sanitize_query("hi\x00there") == "hi there"
