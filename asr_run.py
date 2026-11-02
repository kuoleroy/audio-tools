# -*- coding: utf-8 -*-
"""用 FunASR(Paraformer) 对成品歌跑识别，输出带字级时间戳的 JSON。
用法: python asr_run.py <16k wav> <out.json> [cpu|gpu]
"""
import sys, os, json, time

from lrc_core import models_dir

MODELS = models_dir()
ASR_DIR = os.path.join(MODELS, "paraformer-large_asr_nat-zh-cn-16k-common-vocab8404")
VAD_DIR = os.path.join(MODELS, "fsmn-vad_zh-cn-16k-common")

wav = sys.argv[1]
out = sys.argv[2]
device = sys.argv[3] if len(sys.argv) > 3 else "cpu"

from funasr import AutoModel

t0 = time.time()
model = AutoModel(
    model=ASR_DIR,
    vad_model=VAD_DIR,
    device=device,
    disable_update=True,
    disable_pbar=True,
)
print(f"[load] {time.time()-t0:.1f}s  device={device}", flush=True)

t1 = time.time()
res = model.generate(input=wav, batch_size_s=300, output_timestamp=True)
print(f"[infer] {time.time()-t1:.1f}s", flush=True)

with open(out, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)

print("[keys]", sorted(res[0].keys()))
print("[n_segments]", len(res))
for i, seg in enumerate(res[:3]):
    print(f"--- seg{i} text={seg.get('text','')[:60]!r}")
    for k, v in seg.items():
        if k in ("text",):
            continue
        s = str(v)
        print(f"    {k}: {s[:200]}")
    if "timestamp" in seg:
        ts = seg["timestamp"]
        print(f"    >> timestamp 长度={len(ts)} 前5个={ts[:5]} 末3个={ts[-3:]}")
print("[saved]", out)
