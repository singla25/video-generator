"""S4: Demucs htdemucs vocal/accompaniment split on MPS."""

import resource
import sys
import time

import soundfile as sf
import torch
from demucs.apply import apply_model
from demucs.pretrained import get_model

mix_path, out_prefix, device = sys.argv[1], sys.argv[2], sys.argv[3]
t = time.time()
model = get_model("htdemucs")
model.to(device).eval()
print("load_s", round(time.time() - t, 1), "sources", model.sources)

data, sr = sf.read(mix_path, dtype="float32")
x = torch.from_numpy(data.T)  # (channels, samples)
assert sr == model.samplerate, (sr, model.samplerate)
dur = x.shape[-1] / sr
for i in range(2):
    t = time.time()
    with torch.no_grad():
        out = apply_model(model, x[None], device=device, split=True, progress=False)[0]
    if device == "mps":
        torch.mps.synchronize()
    dt = time.time() - t
    print(f"run{i} device={device} wall_s={dt:.2f} audio_s={dur:.2f} RTF={dt / dur:.2f}")
vocals = out[model.sources.index("vocals")]
rest = out.sum(0) - vocals
sf.write(f"{out_prefix}_vocals.wav", vocals.cpu().numpy().T, sr)
sf.write(f"{out_prefix}_rest.wav", rest.cpu().numpy().T, sr)
print("peak_rss_MB", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20))
