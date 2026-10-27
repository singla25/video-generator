"""S3: Chatterbox-Multilingual Hindi, voice cloned from a Lekha clip (MPS)."""

import resource
import sys
import time

import torch
import soundfile as sf
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

ref, out, device = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "mps"
text = "नमस्कार कृष्ण जी, आपका स्वागत है।"

# Chatterbox checkpoints are saved from CUDA; map them onto the target device.
_orig_load = torch.load
torch.load = lambda *a, **k: _orig_load(*a, **{**k, "map_location": torch.device(device)})

t = time.time()
model = ChatterboxMultilingualTTS.from_pretrained(device=torch.device(device))
print("load_s", round(time.time() - t, 1))
for i in range(2):  # run 2 is warm
    t = time.time()
    wav = model.generate(text, language_id="hi", audio_prompt_path=ref)
    dt = time.time() - t
    dur = wav.shape[-1] / model.sr
    print(f"run{i} device={device} wall_s={dt:.1f} audio_s={dur:.2f} RTF={dt / dur:.2f}")
sf.write(out, wav.cpu().squeeze().numpy(), model.sr)
print("peak_rss_MB", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20))
if device == "mps":
    print("mps_alloc_MB", round(torch.mps.driver_allocated_memory() / 2**20))
