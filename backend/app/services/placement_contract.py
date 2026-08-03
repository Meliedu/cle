"""Facts about the placement test that more than one process must agree on.

Deliberately free of every dependency -- no SQLAlchemy, no config, no models.
Two very different programs need these values and must never disagree about
them: the running API, which gates publication and renders a reviewer's screen,
and the offline extractor under ``scripts/``, which builds the item bank from a
controlled source package on someone's laptop.

Before this existed the extractor kept its own copy of the blocking-flag set,
inverted into an allowlist. Adding a flag code would have left its summary
cheerfully reporting "0 blocking" for a bank the gate would refuse. Anything
both sides reason about belongs here rather than in either of them.
"""
from __future__ import annotations

from typing import Mapping

#: Flag codes that make an item unscoreable, and so stop a version publishing.
#: Anything else is a revision request: real content work, but it does not stop
#: the arithmetic being defensible.
BLOCKING_FLAG_CODES: frozenset[str] = frozenset(
    {"key_disputed", "key_not_in_options", "cloze_blank_number_mismatch"}
)

#: The published blueprint: 12 listening, 6 language use, 12 reading.
EXPECTED_SECTIONS: Mapping[str, int] = {
    "listening": 12,
    "language_use": 6,
    "reading": 12,
}
EXPECTED_ITEMS_PER_FORM = 30
EXPECTED_ITEMS_PER_BAND = 5


def flag_severity(code: str | None) -> str:
    """Whether a content flag stops publication or merely wants a look.

    The single place this judgement is made. Anything that renders a flag needs
    the same answer the preflight reaches, and a second copy of
    :data:`BLOCKING_FLAG_CODES` would drift the first time a code is added --
    showing an advisory note in the styling reserved for an unscoreable item,
    or worse, the reverse.
    """
    return "blocking" if code in BLOCKING_FLAG_CODES else "advisory"
