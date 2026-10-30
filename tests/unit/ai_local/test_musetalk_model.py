"""``_MuseTalkModel`` with fake torch / musetalk / cv2 modules in ``sys.modules`` (no weights)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from vidgen.infrastructure.local_ai import loaders
from vidgen.infrastructure.local_ai import musetalk_support as support
from vidgen.infrastructure.local_ai.errors import LocalAiError

BOX = (10, 10, 50, 50)
PLACEHOLDER = (0.0, 0.0, 0.0, 0.0)


class Frame:
    """An image stand-in with a shape and slicing."""

    def __init__(self, shape: tuple[int, ...] = (100, 100, 3)) -> None:
        self.shape = shape

    def __getitem__(self, key: Any) -> Frame:
        return Frame((40, 40, 3))


class Result:
    """A decoded mouth patch."""

    def astype(self, kind: Any) -> Result:
        return self


class Tensor:
    """Accepts ``.to(...)`` like a torch tensor."""

    def to(self, *args: Any, **kwargs: Any) -> Tensor:
        return self

    def __call__(self, *args: Any, **kwargs: Any) -> Tensor:
        return self


class World:
    """Everything the fakes record, and the knobs tests turn."""

    def __init__(self, *, chunks: int = 3, results: int | None = None) -> None:
        self.chunks = chunks
        self.results = chunks if results is None else results
        self.mps_cleared = 0
        self.written: list[str] = []
        self.landmark_calls = 0
        self.read_calls = 0
        self.boxes: list[Any] = [BOX] * chunks
        self.assembled: list[tuple[Path, int, Path, Path]] = []
        self.fail_in_unet = False


def install(monkeypatch: pytest.MonkeyPatch, world: World, *, mps: bool = False) -> None:
    """Put fake third-party modules into ``sys.modules``."""

    def module(name: str, **attrs: Any) -> types.ModuleType:
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    class NoGrad:
        def __enter__(self) -> None: ...
        def __exit__(self, *exc: Any) -> None: ...

    def empty_cache() -> None:
        world.mps_cleared += 1

    device_type = "mps" if mps else "cpu"
    module(
        "torch",
        device=lambda name: types.SimpleNamespace(type=name),
        no_grad=NoGrad,
        tensor=lambda *a, **k: Tensor(),
        backends=types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: mps)),
        mps=types.SimpleNamespace(empty_cache=empty_cache),
    )
    assert device_type in ("mps", "cpu")
    module("numpy", uint8=object())

    def imwrite(path: str, image: Any) -> None:
        world.written.append(path)
        Path(path).write_bytes(b"png")

    module(
        "cv2",
        INTER_LANCZOS4=4,
        resize=lambda image, size, **k: Frame((size[1], size[0], 3)),
        imwrite=imwrite,
    )
    module("musetalk")
    module("musetalk.utils")

    def landmarks(names: list[str], shift: int) -> tuple[list[Any], list[Frame]]:
        world.landmark_calls += 1
        return list(world.boxes), [Frame() for _ in names]

    def read_imgs(names: list[str]) -> list[Frame]:
        world.read_calls += 1
        return [Frame() for _ in names]

    pre = module(
        "musetalk.utils.preprocessing",
        coord_placeholder=PLACEHOLDER,
        get_landmark_and_bbox=landmarks,
        read_imgs=read_imgs,
    )

    class Vae:
        def __init__(self) -> None:
            self.vae = Tensor()

        def get_latents_for_unet(self, crop: Any) -> Tensor:
            return Tensor()

        def decode_latents(self, predicted: Any) -> list[Result]:
            return [Result() for _ in range(world.results)]

    class Unet:
        def __init__(self) -> None:
            self.model = InnerModel(world)

    util = module(
        "musetalk.utils.utils",
        load_all_model=lambda **k: (Vae(), Unet(), Tensor()),
        datagen=lambda **k: [(Tensor(), Tensor())],
    )
    module("musetalk.utils.blending", get_image=lambda *a, **k: Frame())
    module("musetalk.utils.face_parsing", FaceParsing=lambda **k: object())

    class Audio:
        def __init__(self, feature_extractor_path: str) -> None: ...

        def get_audio_feature(self, path: str) -> tuple[Any, int]:
            return object(), 1

        def get_whisper_chunk(self, *a: Any, **k: Any) -> list[int]:
            return list(range(world.chunks))

    module("musetalk.utils.audio_processor", AudioProcessor=Audio)

    class Whisper:
        @classmethod
        def from_pretrained(cls, path: str) -> Whisper:
            return cls()

        def to(self, **k: Any) -> Whisper:
            return self

        def eval(self) -> Whisper:
            return self

        def requires_grad_(self, flag: bool) -> None: ...

    module("transformers", WhisperModel=Whisper)
    assert pre is not None and util is not None

    def extract(video: Path, folder: Path, count: int, ffmpeg: str = "ffmpeg") -> list[Path]:
        return [folder / f"{i:08d}.png" for i in range(count)]

    def assemble(blended: Path, count: int, video: Path, out: Path, ffmpeg: str = "ffmpeg") -> None:
        world.assembled.append((blended, count, video, out))
        out.write_bytes(b"video")

    monkeypatch.setattr(support, "extract_frames", extract)
    monkeypatch.setattr(support, "assemble_video", assemble)
    monkeypatch.setattr(sys, "path", list(sys.path))


class InnerModel:
    """The UNet's inner model: movable, callable, returns an object with ``.sample``."""

    dtype = "float32"

    def __init__(self, world: World) -> None:
        self._world = world

    def to(self, device: Any) -> InnerModel:
        return self

    def __call__(self, *a: Any, **k: Any) -> Any:
        if self._world.fail_in_unet:
            raise RuntimeError("unet blew up")
        return types.SimpleNamespace(sample=Tensor())


def repo_for(tmp_path: Path) -> Path:
    """A weights dir that looks like a set-up MuseTalk clone."""
    (tmp_path / loaders.MUSETALK_REPO_DIR / "musetalk").mkdir(parents=True)
    return tmp_path


def files(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Placeholder video, audio and output paths."""
    video, audio = tmp_path / "in.mp4", tmp_path / "a.wav"
    video.write_bytes(b"v")
    audio.write_bytes(b"a")
    return video, audio, tmp_path / "out.mp4"


def test_missing_repo_is_a_clear_local_ai_error_naming_the_setup_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, World())
    with pytest.raises(LocalAiError, match="setup_musetalk"):
        loaders.load_musetalk(tmp_path)


def test_run_writes_the_output_and_assembles_all_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(chunks=3)
    install(monkeypatch, world)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    model.run(video, audio, out)
    assert out.read_bytes() == b"video"
    assert len(world.written) == 3
    assert world.assembled[0][1] == 3


def test_run_restores_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, World())
    before = Path.cwd()
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    model.run(video, audio, out)
    assert Path.cwd() == before


def test_second_render_of_the_same_template_uses_the_landmark_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(chunks=3)
    install(monkeypatch, world)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    model.run(video, audio, out)
    model.run(video, audio, tmp_path / "out2.mp4")
    assert world.landmark_calls == 1
    assert world.read_calls == 1


def test_no_face_found_is_a_local_ai_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(chunks=3)
    world.boxes = [PLACEHOLDER] * 3
    install(monkeypatch, world)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    with pytest.raises(LocalAiError, match="no face"):
        model.run(video, audio, out)
    assert not out.exists()


def test_wrong_frame_count_is_a_local_ai_error_and_writes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(chunks=3, results=2)
    install(monkeypatch, world)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    with pytest.raises(LocalAiError, match="unexpected number"):
        model.run(video, audio, out)
    assert not out.exists()
    assert world.assembled == []


def test_memory_is_released_after_success_on_mps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World()
    install(monkeypatch, world, mps=True)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    model.run(video, audio, out)
    assert world.mps_cleared == 1


def test_memory_is_released_even_when_the_render_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World()
    world.fail_in_unet = True
    install(monkeypatch, world, mps=True)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    with pytest.raises(RuntimeError):
        model.run(video, audio, out)
    assert world.mps_cleared == 1


def test_cpu_device_does_not_touch_the_mps_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World()
    install(monkeypatch, world, mps=False)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    model.run(video, audio, out)
    assert world.mps_cleared == 0


def test_temp_work_folder_is_removed_after_a_failed_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    world = World(chunks=3, results=1)
    install(monkeypatch, world)
    model = loaders.load_musetalk(repo_for(tmp_path))
    video, audio, out = files(tmp_path)
    before = set(Path(tempfile.gettempdir()).glob("musetalk-*"))
    with pytest.raises(LocalAiError):
        model.run(video, audio, out)
    assert set(Path(tempfile.gettempdir()).glob("musetalk-*")) == before
