"""S5: download MuseTalk weights from the official HF repos into ./models (cwd)."""

import sys
from pathlib import Path

from huggingface_hub import snapshot_download

root = Path(sys.argv[1])
jobs = [
    ("TMElyralab/MuseTalk", "", ["musetalkV15/*"]),
    ("stabilityai/sd-vae-ft-mse", "sd-vae", ["config.json", "diffusion_pytorch_model.bin"]),
    ("openai/whisper-tiny", "whisper", ["config.json", "pytorch_model.bin", "preprocessor_config.json"]),
    ("yzd-v/DWPose", "dwpose", ["dw-ll_ucoco_384.pth"]),
]
for repo, sub, patterns in jobs:
    snapshot_download(repo, local_dir=str(root / sub) if sub else str(root), allow_patterns=patterns)
    print("ok", repo)
