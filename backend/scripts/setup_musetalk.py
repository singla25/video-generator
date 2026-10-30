"""One-time MuseTalk setup for AI_MODE=local (run by a person, with internet, never by the app).

Usage: python backend/scripts/setup_musetalk.py <weights_dir>

Creates ``<weights_dir>/musetalk/`` with the pinned upstream clone in ``repo/`` (patched for
Apple silicon, see ``musetalk_mac.patch``), the model files in ``repo/models/`` and the face
detector weights in the torch cache. After this the app runs fully offline (ADR-012).
Every step is skipped when already done, so the script is safe to run again.
Pilot weights only, this Mac (DD-31): two weights have no verified licence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/TMElyralab/MuseTalk.git"
REPO_COMMIT = "0a89dec45a0192b824e3cf4daf96c239440c5ed8"
PATCH = Path(__file__).resolve().parent / "musetalk_mac.patch"
# (HF repo, sub-folder under models/, files); mirrors the weights used in the M2 spike.
HF_JOBS = [
    ("TMElyralab/MuseTalk", "", ["musetalkV15/*"]),
    ("stabilityai/sd-vae-ft-mse", "sd-vae", ["config.json", "diffusion_pytorch_model.bin"]),
    (
        "openai/whisper-tiny",
        "whisper",
        ["config.json", "pytorch_model.bin", "preprocessor_config.json"],
    ),
]
FACE_PARSE_DRIVE_ID = "154JgKpzCPW82qINcVieuPH3fZ2e0P812"  # licence unverified (UNVERIFIED_WEIGHTS)


def run(*command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a command and return its result without raising on a non-zero exit."""
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)  # noqa: S603


def clone_and_patch(repo: Path) -> None:
    """Clone the pinned commit and apply the Mac patch once."""
    if not (repo / ".git").is_dir():
        done = run("git", "clone", REPO_URL, str(repo))
        if done.returncode:
            sys.exit(f"git clone failed: {done.stderr[-300:]}")
    if run("git", "checkout", "--quiet", REPO_COMMIT, cwd=repo).returncode:
        sys.exit("could not check out the pinned MuseTalk commit")
    if run("git", "apply", "--check", "--reverse", str(PATCH), cwd=repo).returncode == 0:
        print("patch already applied")
        return
    done = run("git", "apply", str(PATCH), cwd=repo)
    if done.returncode:
        sys.exit(f"patch failed: {done.stderr[-300:]}")
    print("patch applied")


def download_models(models: Path) -> None:
    """Fetch the model files that are on Hugging Face, then the face-parsing weights."""
    from huggingface_hub import snapshot_download

    for repo_id, sub, patterns in HF_JOBS:
        target = models / sub if sub else models
        snapshot_download(repo_id, local_dir=str(target), allow_patterns=patterns)
        print("ok", repo_id)
    parse = models / "face-parse-bisent" / "79999_iter.pth"
    if parse.is_file():
        return
    parse.parent.mkdir(parents=True, exist_ok=True)
    try:
        import gdown
    except ImportError:
        sys.exit(f"install gdown or download Google Drive file {FACE_PARSE_DRIVE_ID} to {parse}")
    gdown.download(id=FACE_PARSE_DRIVE_ID, output=str(parse), quiet=True)


def warm_face_detector() -> None:
    """Instantiate the landmark model once so its weights are cached for offline use."""
    import face_alignment

    face_alignment.FaceAlignment(face_alignment.LandmarksType.TWO_D, device="cpu")
    print("face detector weights cached")


def main() -> None:
    """Run all setup steps for the weights folder given on the command line."""
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1]).resolve() / "musetalk"
    repo = root / "repo"
    root.mkdir(parents=True, exist_ok=True)
    clone_and_patch(repo)
    download_models(repo / "models")
    warm_face_detector()
    print(f"MuseTalk ready in {root}")


if __name__ == "__main__":
    main()
