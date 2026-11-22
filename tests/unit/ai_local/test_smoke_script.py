"""``backend/scripts/local_ai_smoke.py``: finds the name slot with the app's name matcher."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from vidgen.domain.name_match import closeness
from vidgen.domain.values import Word

SCRIPT = Path(__file__).resolve().parents[3] / "backend" / "scripts" / "local_ai_smoke.py"
CONF, CLOSE = 0.6, 0.8
NAME = "Rahul"
MATCH = "राहुल"  # sounds exactly like Rahul
NEAR_A, NEAR_B = "राजुल", "रहुम"  # both about 0.67 close to Rahul
FAR = "नमस्ते"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("local_ai_smoke_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None, f"missing {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StubStt:
    def __init__(self, words: list[Word]) -> None:
        self.words, self.hints, self.released = words, [], 0

    def transcribe(self, audio: Path, hint: str | None = None) -> list[Word]:
        self.hints.append(hint)
        return self.words

    def release(self) -> None:
        self.released += 1


class StubAdapters:
    def __init__(self, words: list[Word]) -> None:
        self.stt = StubStt(words)


class StubTimer:
    def stage(self, name: str, since: float) -> None:
        return None


def w(text: str, start: float, end: float, conf: float = 0.9) -> Word:
    return Word(text, start, end, conf)


@pytest.fixture
def smoke(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load_script()
    monkeypatch.setattr(module, "_run", lambda *command: "")
    return module


def slots(
    smoke: ModuleType,
    words: list[Word],
    tmp_path: Path,
    *,
    manual: Any = None,
    name: str = NAME,
    conf: float = CONF,
    close: float = CLOSE,
) -> tuple[Any, StubAdapters]:
    adapters = StubAdapters(words)
    result = smoke._template_slots(
        adapters, tmp_path / "t.mp4", tmp_path, StubTimer(), manual, name, conf, close
    )
    return result, adapters


SPEECH = [w("नमस्ते", 0.0, 0.8), w(MATCH, 1.0, 1.6), w("जी", 1.9, 2.1)]


def test_roman_name_matches_devanagari_word_with_slot_and_pause(
    smoke: ModuleType, tmp_path: Path
) -> None:
    (found, pauses, sample), _ = slots(smoke, SPEECH, tmp_path)
    assert found == [(1.0, 1.6)]
    assert pauses == [pytest.approx(0.3)]
    assert sample == tmp_path / "voice_sample.wav"


def test_transcription_gets_the_typed_name_as_hint(smoke: ModuleType, tmp_path: Path) -> None:
    _, adapters = slots(smoke, SPEECH, tmp_path)
    assert adapters.stt.hints == [NAME]
    assert adapters.stt.released == 1


def test_first_word_is_no_longer_the_name(smoke: ModuleType, tmp_path: Path) -> None:
    words = [w("नमस्ते", 0.0, 0.8), w(MATCH, 5.0, 5.5)]
    (found, pauses, _), _ = slots(smoke, words, tmp_path)
    assert found == [(5.0, 5.5)]
    assert pauses == [pytest.approx(0.3)]  # last word: default pause


def test_unrelated_name_exits_with_times_and_closeness_only(
    smoke: ModuleType, tmp_path: Path
) -> None:
    words = [w(NEAR_A, 4.52, 4.90), w(FAR, 0.0, 0.8), w(NEAR_B, 6.0, 6.4)]
    with pytest.raises(SystemExit) as exc:
        slots(smoke, words, tmp_path)
    message = str(exc.value)
    assert re.search(r"0\.67 close at 4\.52-4\.90 s", message)
    assert re.search(r"0\.67 close at 6\.00-6\.40 s", message)
    for secret in (NEAR_A, NEAR_B, FAR, NAME, NAME.lower()):
        assert secret not in message


def test_lists_at_most_three_candidates(smoke: ModuleType, tmp_path: Path) -> None:
    words = [w(NEAR_A, float(i), i + 0.4) for i in range(5)]
    with pytest.raises(SystemExit) as exc:
        slots(smoke, words, tmp_path)
    assert len(re.findall(r"close at", str(exc.value))) == 3


def test_no_candidate_says_no_word_is_close(smoke: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        slots(smoke, [w(FAR, 0.0, 0.8)], tmp_path)
    message = str(exc.value)
    assert "no word is close" in message
    assert "close at" not in message
    assert FAR not in message
    assert NAME not in message


def test_low_confidence_close_word_is_a_candidate_not_a_match(
    smoke: ModuleType, tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as exc:
        slots(smoke, [w(MATCH, 1.0, 1.6, conf=0.3)], tmp_path)
    assert re.search(r"1\.00 close at 1\.00-1\.60 s", str(exc.value))


def test_confidence_exactly_at_threshold_is_accepted(smoke: ModuleType, tmp_path: Path) -> None:
    (found, _, _), _ = slots(smoke, [w(MATCH, 1.0, 1.6, conf=0.6)], tmp_path, conf=0.6)
    assert found == [(1.0, 1.6)]


def test_confidence_just_below_threshold_is_refused(smoke: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        slots(smoke, [w(MATCH, 1.0, 1.6, conf=0.59)], tmp_path, conf=0.6)


def test_closeness_exactly_at_threshold_is_accepted(smoke: ModuleType, tmp_path: Path) -> None:
    limit = closeness(NAME, NEAR_A)
    (found, _, _), _ = slots(smoke, [w(NEAR_A, 2.0, 2.4)], tmp_path, close=limit)
    assert found == [(2.0, 2.4)]


def test_closeness_just_above_threshold_is_refused(smoke: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        slots(smoke, [w(NEAR_A, 2.0, 2.4)], tmp_path, close=closeness(NAME, NEAR_A) + 0.01)


def test_manual_slot_does_not_use_the_matcher(
    smoke: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("select_name_slot must not run with --slot")

    monkeypatch.setattr("vidgen.domain.name_match.select_name_slot", boom)
    (found, pauses, _), _ = slots(smoke, SPEECH, tmp_path, manual=[(1.0, 1.6)], name="Zzz")
    assert found == [(1.0, 1.6)]
    assert pauses == [pytest.approx(0.3)]


def test_empty_transcript_exits_with_no_speech_message(smoke: ModuleType, tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no speech found in the template"):
        slots(smoke, [], tmp_path)


def parse(smoke: ModuleType, *argv: str) -> Any:
    return smoke._parse_args(list(argv))


def test_neither_name_nor_slot_is_an_error_naming_both(
    smoke: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        parse(smoke)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--name" in err and "--slot" in err


def test_name_only_is_accepted(smoke: ModuleType) -> None:
    args = parse(smoke, "--name", NAME)
    assert args.name == NAME
    assert args.slots is None


def test_slot_only_is_accepted(smoke: ModuleType) -> None:
    args = parse(smoke, "--slot", "1", "2")
    assert args.slots == [(1.0, 2.0)]
    assert args.name is None


def test_both_given_keeps_the_manual_slots(smoke: ModuleType) -> None:
    args = parse(smoke, "--name", NAME, "--slot", "3", "4", "--slot", "1", "2")
    assert args.slots == [(1.0, 2.0), (3.0, 4.0)]
    assert args.name == NAME


@pytest.mark.parametrize("bad", [("2", "1"), ("1", "1"), ("-1", "2")])
def test_invalid_slot_values_are_still_rejected(
    smoke: ModuleType, capsys: pytest.CaptureFixture[str], bad: tuple[str, str]
) -> None:
    with pytest.raises(SystemExit):
        parse(smoke, "--name", NAME, "--slot", *bad)
    assert "--slot needs START" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["a/b", "../x", "/abs"])
def test_out_name_must_be_a_plain_folder_name(
    smoke: ModuleType, capsys: pytest.CaptureFixture[str], bad: str
) -> None:
    with pytest.raises(SystemExit):
        parse(smoke, "--name", NAME, "--out-name", bad)
    assert "plain folder name" in capsys.readouterr().err


def test_plain_out_name_is_accepted(smoke: ModuleType) -> None:
    assert parse(smoke, "--name", NAME, "--out-name", "run1").out_name == "run1"
