# -*- coding: utf-8 -*-
"""用 FSMN-VAD 单独切出唱句边界（不识别文字），用于把歌词行按顺序对到时间轴上。
用法: python vad_segments.py <wav> <out.json>
"""
import sys, os, json

MODELS = r"C:\Users\admin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\asr"
VAD_DIR = os.path.join(MODELS, "fsmn-vad_zh-cn-16k-common")

wav, out = sys.argv[1], sys.argv[2]

from funasr import AutoModel
m = AutoModel(model=VAD_DIR, device="cuda", disable_update=True, disable_pbar=True)

res = m.generate(input=wav)
segs = []
for r in res:
    for s in (r.get("value") or []):
        if isinstance(s, (list, tuple)) and len(s) >= 2:
            segs.append([int(s[0]), int(s[1])])
segs.sort()
json.dump(segs, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"[vad] {len(segs)} 段 -> {out}")
for i, (a, b) in enumerate(segs):
    print(f"  {i:3d}  {a/1000:7.2f}s - {b/1000:7.2f}s  ({(b-a)/1000:5.2f}s)")
