"""BL-11: SpellingFiller fills the missing spoken names of a batch (test ids SP-*).

Contract: docs/test-tree/bl11-spellings-for-all-rows.md. Everything here uses in-memory doubles.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from tests.fixtures.spelling_fakes import FakeTransliterator, InMemorySpellingStore
from vidgen.services.spelling_filler import PAGE_SIZE, SpellingFiller, SpellingReport

CANARY = "Zeenat-Canary"
CANARY_SPELLING = "ज़ीनत-कैनरी"


def make(
    store: InMemorySpellingStore,
    translit: FakeTransliterator,
    page_size: int = PAGE_SIZE,
) -> SpellingFiller:
    return SpellingFiller(store, translit, spoken_script="devanagari", page_size=page_size)


# ---- positive -------------------------------------------------------------------------


def test_every_queued_row_without_a_spoken_name_gets_a_spelling() -> None:
    """SP-P1."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha", "Bina", "Chitra"])
    report = make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == ["देव-Asha", "देव-Bina", "देव-Chitra"]
    assert report == SpellingReport(filled=3, skipped=0, failed=0)


def test_the_transliterator_gets_the_row_name_and_the_spoken_script() -> None:
    """SP-P2."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    make(store, translit).fill_missing(store.add_batch(["Asha"]))
    assert translit.calls == [("Asha", "devanagari")]


def test_the_default_page_size_is_fifty() -> None:
    """SP-P3."""
    store = InMemorySpellingStore()
    make(store, FakeTransliterator()).fill_missing(store.add_batch(["Asha"]))
    assert PAGE_SIZE == 50
    assert store.page_limits and set(store.page_limits) == {50}


def test_release_is_called_once_after_a_successful_run() -> None:
    """SP-P4."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    make(store, translit).fill_missing(store.add_batch(["Asha", "Bina"]))
    assert translit.released == 1


def test_a_second_run_changes_nothing_and_asks_nothing() -> None:
    """SP-P5: idempotent."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha", "Bina"])
    filler = make(store, translit)
    filler.fill_missing(batch)
    first = store.spoken(batch)
    calls = len(translit.calls)
    report = filler.fill_missing(batch)
    assert store.spoken(batch) == first
    assert len(translit.calls) == calls
    assert report == SpellingReport(filled=0, skipped=0, failed=0)


# ---- negative -------------------------------------------------------------------------


def test_a_spoken_name_from_the_sheet_is_never_overwritten() -> None:
    """SP-N1."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha", "Bina"])
    store.rows[batch][0].spoken = "आशा"
    make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == ["आशा", "देव-Bina"]
    assert [name for name, _ in translit.calls] == ["Bina"]


@pytest.mark.parametrize("status", ["PROCESSING", "COMPLETED", "FAILED", "SKIPPED", "CANCELLED"])
def test_rows_that_are_not_queued_are_untouched(status: str) -> None:
    """SP-N2."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha"], status=status)
    make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == [None]
    assert translit.calls == []


@pytest.mark.parametrize("result", ["", "   ", "\n\t", None])
def test_a_blank_or_missing_result_is_skipped_not_stored(result: str | None) -> None:
    """SP-N3."""
    store, translit = InMemorySpellingStore({}), FakeTransliterator({"Asha": result})
    batch = store.add_batch(["Asha", "Bina"])
    report = make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == [None, "देव-Bina"]
    assert (report.filled, report.skipped, report.failed) == (1, 1, 0)


def test_one_failing_row_is_counted_and_the_others_continue() -> None:
    """SP-N4."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    translit.errors["Bina"] = RuntimeError("model crashed")
    batch = store.add_batch(["Asha", "Bina", "Chitra"])
    report = make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == ["देव-Asha", None, "देव-Chitra"]
    assert (report.filled, report.failed) == (2, 1)


def test_release_is_called_even_when_every_row_fails() -> None:
    """SP-N5."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    translit.default = lambda name: (_ for _ in ()).throw(RuntimeError("boom"))
    report = make(store, translit).fill_missing(store.add_batch(["Asha", "Bina"]))
    assert report.failed == 2
    assert translit.released == 1


def test_release_is_called_when_the_store_itself_breaks() -> None:
    """SP-N6: an unexpected error from the store still frees the model."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha"])

    def broken(*_: object, **__: object) -> list[object]:
        raise ConnectionError("db down")

    store.rows_missing_spoken_name = broken  # type: ignore[method-assign,assignment]
    with pytest.raises(ConnectionError):
        make(store, translit).fill_missing(batch)
    assert translit.released == 1


def test_a_store_error_for_one_row_does_not_stop_the_others() -> None:
    """SP-N7."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    store.set_errors["Asha"] = OSError("write failed")
    batch = store.add_batch(["Asha", "Bina"])
    report = make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == [None, "देव-Bina"]
    assert (report.filled, report.failed) == (1, 1)


def test_a_row_that_got_a_spoken_name_meanwhile_keeps_it() -> None:
    """SP-N8: compare-and-set, the late writer does not win."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha", "Bina"])

    def concurrent(row: object) -> None:
        if row.name == "Asha":
            row.spoken = "मानव"

    store.before_set = concurrent
    report = make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == ["मानव", "देव-Bina"]
    assert report.skipped == 1 and report.filled == 1


def test_a_row_claimed_meanwhile_is_not_changed() -> None:
    """SP-N9: the render claimed the row between page read and write."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha"])

    def claim(row: object) -> None:
        row.status = "PROCESSING"

    store.before_set = claim
    make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == [None]


def test_an_unknown_or_deleted_batch_is_a_quiet_no_op() -> None:
    """SP-N10."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha"])
    store.delete_batch(batch)
    report = make(store, translit).fill_missing(batch)
    assert report == SpellingReport(0, 0, 0)
    assert translit.released == 1
    assert make(store, translit).fill_missing(uuid4()) == SpellingReport(0, 0, 0)


def test_other_batches_are_never_touched() -> None:
    """SP-N11."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    mine, other = store.add_batch(["Asha"]), store.add_batch(["Bina"])
    make(store, translit).fill_missing(mine)
    assert store.spoken(other) == [None]


# ---- edge -----------------------------------------------------------------------------


def test_an_empty_batch_finishes_cleanly_and_releases() -> None:
    """SP-E1."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    report = make(store, translit).fill_missing(store.add_batch([]))
    assert report == SpellingReport(0, 0, 0)
    assert translit.released == 1


def test_a_single_row_batch() -> None:
    """SP-E2."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch(["Asha"])
    assert make(store, translit).fill_missing(batch).filled == 1


@pytest.mark.parametrize("count", [3, 4, 5, 7])
def test_more_rows_than_one_page_are_all_filled(count: int) -> None:
    """SP-E3: page size 3 covers exact multiples and remainders."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch([f"Name{n}" for n in range(count)])
    report = make(store, translit, page_size=3).fill_missing(batch)
    assert None not in store.spoken(batch)
    assert report.filled == count
    assert set(store.page_limits) == {3}


def test_blank_results_across_several_pages_do_not_loop_forever() -> None:
    """SP-E4: skipped rows stay missing, so the cursor must move past them."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    translit.default = lambda name: ""
    batch = store.add_batch([f"N{n}" for n in range(7)])
    report = make(store, translit, page_size=2).fill_missing(batch)
    assert report.skipped == 7
    assert len(store.page_limits) <= 6


@pytest.mark.parametrize("name", ["Zoë O'Brien-Smith", "كريم", "😀 Kabir", "x" * 200, "A"])
def test_unicode_emoji_rtl_and_very_long_names_are_handled(name: str) -> None:
    """SP-E5."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    batch = store.add_batch([name])
    make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == [f"देव-{name}"]


def test_a_long_spelling_is_stored_whole() -> None:
    """SP-E6."""
    store = InMemorySpellingStore()
    translit = FakeTransliterator({"Asha": "आ" * 400})
    batch = store.add_batch(["Asha"])
    make(store, translit).fill_missing(batch)
    assert store.spoken(batch) == ["आ" * 400]


def test_rerun_after_a_partial_failure_fills_only_what_is_missing() -> None:
    """SP-E7: a retried job is safe."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    translit.errors["Bina"] = RuntimeError("once")
    batch = store.add_batch(["Asha", "Bina"])
    filler = make(store, translit)
    filler.fill_missing(batch)
    del translit.errors["Bina"]
    translit.calls.clear()
    report = filler.fill_missing(batch)
    assert store.spoken(batch) == ["देव-Asha", "देव-Bina"]
    assert [n for n, _ in translit.calls] == ["Bina"]
    assert report.filled == 1


def test_no_name_or_spelling_is_ever_logged(caplog: pytest.LogCaptureFixture) -> None:
    """SP-E8: counts and error types only."""
    store = InMemorySpellingStore()
    translit = FakeTransliterator({CANARY: CANARY_SPELLING})
    translit.errors["Boom-Canary"] = ValueError("bad input Boom-Canary")
    batch = store.add_batch([CANARY, "Boom-Canary"])
    with caplog.at_level(logging.DEBUG):
        make(store, translit).fill_missing(batch)
    assert caplog.records, "the job should log its counts"
    text = " ".join(
        f"{r.getMessage()} {sorted(r.__dict__.items(), key=str)} {r.exc_text} {r.exc_info}"
        for r in caplog.records
    )
    for secret in (CANARY, CANARY_SPELLING, "Boom-Canary", "bad input"):
        assert secret not in text


def test_the_error_type_of_a_failing_row_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    """SP-E9."""
    store, translit = InMemorySpellingStore(), FakeTransliterator()
    translit.errors["Asha"] = KeyError("x")
    with caplog.at_level(logging.DEBUG):
        make(store, translit).fill_missing(store.add_batch(["Asha"]))
    assert any("KeyError" in f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
