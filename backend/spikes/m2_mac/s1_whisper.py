"""S1: faster-whisper word timestamps on CPU."""

import resource
import sys
import time

from faster_whisper import WhisperModel

wav = sys.argv[1]
size = sys.argv[2] if len(sys.argv) > 2 else "small"
t = time.time()
m = WhisperModel(size, device="cpu", compute_type="int8")
load = time.time() - t
t = time.time()
segs, info = m.transcribe(wav, language="hi", word_timestamps=True)
words = [(w.word, round(w.start, 2), round(w.end, 2)) for s in segs for w in s.words]
run = time.time() - t
print("model", size, "load_s", round(load, 1), "run_s", round(run, 2))
for w in words:
    print(w)
print("peak_rss_MB", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20))
