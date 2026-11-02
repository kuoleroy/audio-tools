# -*- coding: utf-8 -*-
"""分块跑 Paraformer 再合并：长音频直接跑会崩（CIF 累积误差），短块逐个跑才准。

策略：
1. 用短时能量找出「最安静的点」作为切点，避免从字中间切开；
2. 每块 20 秒左右、互相重叠 8 秒；
3. 逐块识别，字符时间戳加上块偏移变成绝对时间；
4. 重叠区按「块中心更近」原则去重，每字只留一次。

用法: python asr_chunked.py <wav> <out.json> [chunk_sec] [overlap_sec]
"""
import sys, os, json, wave, time
import numpy as np

wav_path, out_path = sys.argv[1], sys.argv[2]
CHUNK = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
OVER = float(sys.argv[4]) if len(sys.argv) > 4 else 8.0

MODELS = os.environ.get(
    "ASR_MODELS", r"C:\Users\admin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\asr")
ASR_DIR = os.path.join(MODELS, "paraformer-large_asr_nat-zh-cn-16k-common-vocab8404")
VAD_DIR = os.path.join(MODELS, "fsmn-vad_zh-cn-16k-common")

# ---------- 读音频算能量，找静音切点 ----------
w = wave.open(wav_path, "rb")
sr = w.getframerate(); n = w.getnframes()
audio = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
w.close()
total = n / sr
hop = int(sr * 0.02)
nfr = len(audio) // hop
frames = audio[: nfr * hop].reshape(nfr, hop)
rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)

def quietest_at(t, win=2.5):
    """在 t 附近 ±win 秒里找能量最低的 20ms 帧，返回该时刻"""
    lo = max(0, int((t - win) / 0.02))
    hi = min(nfr, int((t + win) / 0.02))
    if hi <= lo:
        return t
    i = lo + int(np.argmin(rms[lo:hi]))
    return i * 0.02

# ---------- 规划块 ----------
# 领地边界 b：每 STEP 秒一个边界，边界落在最安静的点上。
# 第 k 块的「识别窗口」= [b[k], b[k]+CHUNK]（比领地长 OVER，所以有重叠）
# 第 k 块的「领地」= [b[k], b[k+1])（互不重叠，合并时每块只认领自己的领地）
STEP = CHUNK - OVER
bounds = [0.0]
while bounds[-1] + STEP < total - 1.0:
    nxt = quietest_at(min(bounds[-1] + STEP, total - 2.0))
    if nxt <= bounds[-1]:
        nxt = bounds[-1] + STEP
    bounds.append(nxt)
bounds.append(total)
print(f"[plan] {len(bounds)-1} 块 | 领地边界: " + " ".join(f"{c:.1f}" for c in bounds))
print(f"[plan] 每块识别窗口 {CHUNK:.0f}s，领地 {STEP:.0f}s，重叠 {OVER:.0f}s")

# ---------- 识别 ----------
from funasr import AutoModel
model = AutoModel(model=ASR_DIR, vad_model=VAD_DIR, device="cuda",
                  disable_update=True, disable_pbar=True)

import subprocess, tempfile
tmpdir = tempfile.mkdtemp(prefix="asrchk_")
pieces = []   # (window_start, window_end, territory_start, territory_end, chars)
for k in range(len(bounds) - 1):
    a = bounds[k]
    b = min(a + CHUNK, total)
    if b - a < 1.0:
        continue
    terr_a = bounds[k]
    terr_b = bounds[k + 1]
    seg = os.path.join(tmpdir, f"c{k}.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
                    "-i", wav_path, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", seg],
                   check=True)
    res = model.generate(input=seg, batch_size_s=300, output_timestamp=True)
    chars = []
    for r in res:
        txt = r.get("text", "") or ""
        ts = r.get("timestamp") or []
        for j, ch in enumerate(txt):
            if ch.isspace():
                continue
            if j < len(ts):
                chars.append((ch, ts[j][0] + a * 1000, ts[j][1] + a * 1000))
            else:
                chars.append((ch, None, None))
    pieces.append((a, b, terr_a, terr_b, chars))
    print(f"[chunk {k}] 窗口{a:6.1f}-{b:6.1f} 领地{terr_a:6.1f}-{terr_b:6.1f} "
          f"{len(chars):3d}字  {''.join(c[0] for c in chars)[:44]}", flush=True)

# ---------- 合并：序列级拼接 ----------
# 重叠区里两个块可能认出不同的字，逐字按时间混排会把顺序打乱。
# 改成「接龙」：把新块的文字跟已合并文本的尾巴做序列对齐，
# 只把没匹配上的后半截追加进去 —— 既不重复也不打乱顺序。
import difflib

global_chars = []      # (char, start_ms, end_ms)
for a, b, terr_a, terr_b, chars in pieces:
    if not chars:
        continue
    ctext = "".join(ch for ch, _, _ in chars)
    gtext = "".join(ch for ch, _, _ in global_chars)
    if gtext:
        sm = difflib.SequenceMatcher(None, gtext, ctext, autojunk=False)
        blocks = [blk for blk in sm.get_matching_blocks() if blk.size > 0]
        if blocks:
            last = max(blocks, key=lambda blk: blk.b + blk.size)
            cut = last.b + last.size
        else:
            cut = 0
    else:
        cut = 0
    for ch, s, e in chars[cut:]:
        global_chars.append((ch, s, e))

global_chars.sort(key=lambda x: x[1])
# paraformer 的字级时间戳会互相重叠，只丢掉几乎同起点（<25ms）的真重复
out, last_start = [], -1e9
for s, e, ch in global_chars:
    if s < last_start + 25:
        continue
    out.append((s, e, ch))
    last_start = s

json.dump({"key": os.path.basename(wav_path),
           "text": " ".join(c for _, _, c in out),
           "timestamp": [[int(s), int(e)] for s, e, _ in out]},
          open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n[out] {out_path}  {len(out)} 字")
print("[text]", " ".join(c for _, _, c in out))
