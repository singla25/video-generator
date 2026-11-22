# Kaggle trial on 2x Tesla T4 (one GPU used)

Try the speech-to-text and voice-cloning models by hand on a free Kaggle GPU. **Kaggle is a third party: use only made-up
demo data** (the notebook makes its own test audio with the default made-up voice). No voter data, no real person's voice,
no tokens or passwords in the notebook (C5). This is a measurement trial, not a render worker: the app never connects to Kaggle.

Settings in the notebook: **Accelerator = GPU T4 x2** (the code uses only GPU 0), **Internet = On**.
Nothing here was run by me; it is untested on your machine. Paste the printed summary back to me.
No upload is needed: Cell 5 makes its own test audio with the default made-up voice and Cell 4 listens to it.

**Reading the cell names:** Kaggle numbers cells by the order you run them (`[1]`, `[2]`, ...), not by the names used here. Our
**Cell 5 (voice) runs before Cell 4 (Whisper)**, so the Kaggle number shown next to a cell will not match its name here. Follow the
run order below, not the numbers on the screen.

## Run order
**Cell 1, Cell 2, restart the kernel, Cell 1, Cell 3a, Cell 3b, Cell 5, Cell 4, Cell 6.**
(Cell 1 runs twice because the restart forgets the one-GPU setting. Cell 5 comes before Cell 4 because Cell 4 reads the
audio file that Cell 5 writes.)

## Cell 1: pick ONE GPU (run this first in a fresh session)
```python
import os
os.environ["CUDA_VISIBLE_DEVICES"] = "0"      # one T4; must be set before torch or ctranslate2 are imported
os.environ["TOKENIZERS_PARALLELISM"] = "false"
import subprocess
print(subprocess.run(["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv"],
                     capture_output=True, text=True).stdout)
import torch
print("torch", torch.__version__, "| gpus visible:", torch.cuda.device_count(), "|", torch.cuda.get_device_name(0))
print("arch list:", torch.cuda.get_arch_list())   # must contain sm_75 (T4)
print(torch.zeros(1).cuda() + 1)                  # a real kernel runs
```

## Cell 2: install, KEEP the preinstalled torch (no torch install)
**Kaggle runs Python 3.13.** The old exact pins (`omegaconf==2.0.6`, `numpy==1.26.4` and the others) were for the MuseTalk
setup and the Mac. Python 3.13's pip refuses `omegaconf==2.0.6` (invalid metadata) and numpy 1.26.4 has no Python 3.13 build, so
they are gone. Only three pins stay: `faster-whisper==1.2.1`, `transformers==5.20.2` and `chatterbox-tts==0.1.7`. Everything
else is installed unpinned, so pip picks versions that work on 3.13 and keeps Kaggle's own numpy.
Chatterbox 0.1.7 pins an old torch and `transformers==5.2.0`; those pins are stale, so we add Chatterbox with `--no-deps`.
pip then never replaces the preinstalled `torch 2.11.0+cu130`.
```python
%%bash
python --version
python -c "import torch, torchaudio, numpy; print('before:', torch.__version__, torchaudio.__version__, 'numpy', numpy.__version__)"
pip install -q "faster-whisper==1.2.1" "transformers==5.20.2"
# Chatterbox's own dependencies, unpinned. Each one separately, so one failure does not hide the others.
for p in accelerate librosa s3tokenizer diffusers resemble-perth conformer safetensors pykakasi pyloudnorm omegaconf soundfile huggingface_hub; do
  pip install -q "$p" || echo "FAILED: $p"
done
pip install -q --no-deps "chatterbox-tts==0.1.7"
python -c "import torch, numpy; print('after: ', torch.__version__, 'numpy', numpy.__version__)"   # torch must be unchanged
```
**Then restart the kernel** (Run menu, Restart session) to be safe, and run Cell 1 again before Cell 3a.
If `after:` shows a different torch, or any line says `FAILED: <package>`, stop and send me the output.

## Cell 3a: install the CUDA 12 and cuDNN 9 libraries (pip only)
faster-whisper runs on CTranslate2, which needs CUDA 12 cuBLAS and cuDNN 9. The machine has CUDA 13, so add the CUDA 12
libraries as pip wheels.
```python
%%bash
pip install -q "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
```

## Cell 3b: load those libraries (plain Python, no %%bash)
Run this in its own cell, after 3a and before anything uses faster-whisper.
```python
import ctypes, glob, os, sysconfig
site = sysconfig.get_paths()["purelib"]
libdirs = sorted(glob.glob(os.path.join(site, "nvidia", "*", "lib")))
os.environ["LD_LIBRARY_PATH"] = ":".join(libdirs + [os.environ.get("LD_LIBRARY_PATH", "")])   # for any subprocess
for pat in ["cublas/lib/libcublasLt.so.12", "cublas/lib/libcublas.so.12", "cudnn/lib/libcudnn*.so.9"]:
    for path in sorted(glob.glob(os.path.join(site, "nvidia", pat))):
        ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)       # load now, before ctranslate2 asks for them
print("preloaded from", len(libdirs), "nvidia lib folders")
```

## Cell 4: speech-to-text, small and medium, float16 on the GPU (run after Cell 5)
It listens to the file Cell 5 wrote (made-up default voice, no upload). Success looks like a word list that contains
`राहुल` with a time inside the clip; note which size writes it correctly.
```python
import gc, subprocess, time
import librosa
import torch
from faster_whisper import WhisperModel

AUDIO = "/kaggle/working/default_warm.wav"        # written by Cell 5 (made-up default voice)
NAME = "Rahul"                                    # the name typed in the template (used as a hint)

# Workaround for the Kaggle PyAV mismatch: faster-whisper 1.2.1 would decode the file itself through PyAV and fail with
# "TypeError: open() got an unexpected keyword argument 'metadata_errors'". Load the samples with librosa and pass the array.
audio, _ = librosa.load(AUDIO, sr=16000, mono=True)

def gpu_mib():
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout.split()[0]
    return int(out)

stt_rows = []
for size in ("small", "medium"):
    t = time.time()
    model = WhisperModel(size, device="cuda", compute_type="float16")   # T4: float16, no fast bf16
    load_s = time.time() - t
    used = gpu_mib()
    t = time.time()
    segments, _ = model.transcribe(audio, language="hi", word_timestamps=True, hotwords=NAME)
    words = [(w.word.strip(), round(w.start, 2), round(w.end, 2), round(w.probability, 2))
             for s in segments for w in (s.words or [])]
    run_s = time.time() - t
    stt_rows.append((size, round(load_s, 1), round(run_s, 2), used))
    print(size, "load", round(load_s, 1), "s | run", round(run_s, 2), "s | GPU used", used, "MiB")
    print(words)
    del model; gc.collect(); torch.cuda.empty_cache()
```
Run it a second time to see the warm run time (the first run includes CUDA start-up).

## Cell 5: Chatterbox voice on the GPU (run before Cell 4)
Uses the default made-up voice (`VOICE = None`), so there is nothing to upload. It writes `default_first.wav` and
`default_warm.wav`, then frees the voice model so Cell 4 has the whole GPU.
```python
import time, gc
import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from IPython.display import Audio, display

VOICE = None   # default made-up voice; nothing to upload
TEXT = "नमस्ते राहुल जी, आपका स्वागत है।"
FILES = ["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json",
         "conds.pt", "Cangjie5_TC.json"]
ckpt = snapshot_download("ResembleAI/chatterbox", allow_patterns=FILES, local_dir="/kaggle/working/chatterbox")

t = time.time()
tts = ChatterboxMultilingualTTS.from_local(ckpt, torch.device("cuda"))
print("load", round(time.time() - t, 1), "s | t3 dtype:", next(tts.t3.parameters()).dtype)

def speak(label, autocast=False):
    torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); t0 = time.time()
    kw = dict(language_id="hi")
    if VOICE:
        kw["audio_prompt_path"] = VOICE
    if autocast:
        with torch.autocast("cuda", dtype=torch.float16):
            wav = tts.generate(TEXT, **kw)
    else:
        wav = tts.generate(TEXT, **kw)
    torch.cuda.synchronize()
    secs = time.time() - t0
    peak = torch.cuda.max_memory_allocated() // (1 << 20)
    print(label, "| time", round(secs, 2), "s | audio", round(wav.shape[-1] / tts.sr, 2), "s | peak", peak, "MiB")
    sf.write(f"/kaggle/working/{label}.wav", wav.cpu().squeeze().numpy(), int(tts.sr))
    display(Audio(f"/kaggle/working/{label}.wav"))
    return secs, peak

speak("default_first")     # includes warm-up
speak("default_warm")      # this file is the input of Cell 4
# optional experiment, only if the two runs above work: speak("fp16_autocast", autocast=True)

del tts                    # free the voice model before the speech-to-text cell
gc.collect()
torch.cuda.empty_cache()
```
Optional experiment: `speak("fp16_autocast", autocast=True)` (run it before the `del tts` lines). T4 has no fast bf16, so check
that the dtype line above is not bfloat16, and compare time and listen to the audio (float16 can change quality or fail).

## Cell 6: summary to paste back
```python
print("STT (size, load s, run s, GPU MiB):", stt_rows)
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv"], capture_output=True, text=True).stdout)
```
Send me this output, the printed word lists from Cell 4, the dtype line and the Chatterbox timing lines.

## Where it could fail
- **PyAV mismatch (found in the second trial):** faster-whisper 1.2.1 on Kaggle (Python 3.13) fails with
  `TypeError: open() got an unexpected keyword argument 'metadata_errors'` (from `av.container.core.open` via
  `faster_whisper.audio.decode_audio`): the installed PyAV does not match what faster-whisper expects. Cell 4 works around it by
  loading the audio with `librosa.load(..., sr=16000, mono=True)` and passing the numpy array to `model.transcribe`.
  **A future GPU image (for any cloud option) must pin a PyAV (`av`) version that is compatible with the pinned faster-whisper**,
  or load audio the same way, because file decoding is on the real path there.
- **Python 3.13 (found in the first trial):** Kaggle's Python is 3.13. Exact old pins can be refused by its pip or have no 3.13
  build (`omegaconf==2.0.6`, `numpy==1.26.4` did), so Cell 2 pins only faster-whisper, transformers and Chatterbox. An unpinned
  package may still fail on 3.13 (the likely suspects are `resemble-perth`, `s3tokenizer`, `pykakasi`): Cell 2 prints
  `FAILED: <package>` and goes on. Send me that line.
- **numpy 2:** Kaggle keeps its own numpy (version printed before and after). Chatterbox's metadata asks for an old numpy, which
  we ignore with `--no-deps`; if an import then fails with a numpy error, send me the message.
- **Chatterbox on the preinstalled torch:** untested. We only tested it on torch 2.14.1 on the Mac. If Cell 5 fails on import
  or on the first generate, send me the full error.
- **bfloat16:** if the `t3 dtype` line says bfloat16, the T4 runs it slowly. Tell me and I will adjust.
- **cuDNN preload:** if Cell 3b loads but Whisper still cannot find cuDNN, send me the exact error.

## Afterwards
Delete the uploaded dataset and the outputs, and turn Internet off. Nothing from this notebook goes into the project database.
