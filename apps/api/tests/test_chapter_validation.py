"""Chapter rule validation (spec feature 10, 12): starts at 00:00, >=3
chapters, strictly ascending, each >=10s apart.
"""

from __future__ import annotations

from creatoriqx_api.modules.content.domain.chapters import Chapter, validate_chapters


def _chapters(*pairs: tuple[int, str]) -> tuple[Chapter, ...]:
    return tuple(Chapter(start_seconds=s, title=t) for s, t in pairs)


def test_a_well_formed_chapter_list_has_no_violations() -> None:
    chapters = _chapters((0, "Intro"), (30, "Main"), (90, "Outro"))
    assert validate_chapters(chapters) == []


def test_fewer_than_three_chapters_is_rejected() -> None:
    reasons = validate_chapters(_chapters((0, "Intro"), (30, "Main")))
    assert any("at least 3" in r for r in reasons)


def test_first_chapter_must_start_at_zero() -> None:
    reasons = validate_chapters(_chapters((5, "Intro"), (30, "Main"), (90, "Outro")))
    assert any("00:00" in r for r in reasons)


def test_start_times_must_be_strictly_ascending() -> None:
    reasons = validate_chapters(_chapters((0, "Intro"), (30, "Main"), (30, "Outro")))
    assert any("ascending" in r for r in reasons)


def test_descending_start_times_are_rejected() -> None:
    reasons = validate_chapters(_chapters((0, "Intro"), (90, "Main"), (30, "Outro")))
    assert any("ascending" in r for r in reasons)


def test_chapters_closer_than_ten_seconds_are_rejected() -> None:
    reasons = validate_chapters(_chapters((0, "Intro"), (5, "Main"), (30, "Outro")))
    assert any("at least 10s" in r for r in reasons)


def test_empty_chapter_list_only_reports_the_count_violation() -> None:
    reasons = validate_chapters(())
    assert reasons == ["needs at least 3 chapters, got 0"]
