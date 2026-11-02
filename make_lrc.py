# -*- coding: utf-8 -*-
"""直接出 LRC：分块识别 → 全局对齐歌词 → 逐行时间（单调、不倒流）。

要点：
- 长音频整跑会崩（CIF 累积误差），必须切块（≤20s）逐块识别；
- 切块不重叠，避免同一段被认两遍导致文字互相打架；
- 全文与歌词做编辑距离对齐（允许替换匹配：起↔妻、道行↔舞蹈），
  对上的字搬时间戳；认不出的行按前后锚点插值；
- 最后强制单调：行与行之间时间不倒流、间隔不小于 1 秒。

用法: python make_lrc.py <vocals_16k.wav> <lyrics.txt> <out.lrc> [report.json]
"""
import sys, os, json, wave, subprocess, tempfile
import numpy as np

wav_path, lyric_txt, out_lrc = sys.argv[1], sys.argv[2], sys.argv[3]
report_json = sys.argv[4] if len(sys.argv) > 4 else None

MODELS = r"C:\Users\admin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\asr"
ASR_DIR = os.path.join(MODELS, "paraformer-large_asr_nat-zh-cn-16k-common-vocab8404")
VAD_DIR = os.path.join(MODELS, "fsmn-vad_zh-cn-16k-common")

CHUNK = 20.0          # 块长；块与块不重叠
MIN_GAP = 1.0         # 相邻两行最小间隔（秒）

# ---------- 读歌词 ----------
lines = []
for ln in open(lyric_txt, encoding="utf-8").read().splitlines():
    ln = ln.strip()
    if ln:
        lines.append(ln)
ref, line_spans = [], []
for ln in lines:
    s = len(ref)
    for ch in ln:
        if not ch.isspace():
            ref.append(ch)
    line_spans.append((s, len(ref)))
print(f"[ref] {len(lines)} 行 / {len(ref)} 字")

# ---------- 能量包络 → 安静切点 ----------
w = wave.open(wav_path, "rb")
sr = w.getframerate(); n = w.getnframes()
audio = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
w.close()
total = n / sr
hop = int(sr * 0.02)
nfr = len(audio) // hop
rms = np.sqrt((audio[: nfr * hop].reshape(nfr, hop) ** 2).mean(axis=1) + 1e-12)


def quietest_at(t, win=2.0):
    lo = max(0, int((t - win) / 0.02))
    hi = min(nfr, int((t + win) / 0.02))
    if hi <= lo:
        return t
    return (lo + int(np.argmin(rms[lo:hi]))) * 0.02


bounds = [0.0]
while bounds[-1] + CHUNK < total - 1.0:
    nxt = quietest_at(min(bounds[-1] + CHUNK, total - 2.0))
    bounds.append(nxt if nxt > bounds[-1] + 8 else bounds[-1] + CHUNK)
bounds.append(total)
print(f"[plan] {len(bounds)-1} 块（不重叠）")

# ---------- 编辑距离对齐（带回溯） ----------
def align(ref, hyp):
    n, m = len(ref), len(hyp)
    rows = [list(range(m + 1))]
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        ri, prev = ref[i - 1], rows[-1]
        for j in range(1, m + 1):
            cost = 0 if ri == hyp[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        rows.append(cur)
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        ri, hj = ref[i - 1], hyp[j - 1]
        cost = 0 if ri == hj else 1
        if rows[i][j] == rows[i - 1][j - 1] + cost:
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif rows[i][j] == rows[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


# ---------- 逐块识别，拼成完整文本 ----------
from funasr import AutoModel
model = AutoModel(model=ASR_DIR, vad_model=VAD_DIR, device="cuda",
                  disable_update=True, disable_pbar=True)

tmpdir = tempfile.mkdtemp(prefix="mkLRC_")
hyp, htimes = [], []
for k in range(len(bounds) - 1):
    a, b = bounds[k], bounds[k + 1]
    if b - a < 1.0:
        continue
    seg = os.path.join(tmpdir, f"c{k}.wav")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
                    "-i", wav_path, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", seg],
                   check=True)
    res = model.generate(input=seg, batch_size_s=300, output_timestamp=True)
    cs = []
    for r in res:
        txt, ts = r.get("text", "") or "", r.get("timestamp") or []
        j = 0
        for ch in txt:
            if ch.isspace():
                continue
            if j < len(ts):
                cs.append((ch, ts[j][0] + a * 1000, ts[j][1] + a * 1000))
            j += 1
    hyp.extend(cs)
    print(f"[chunk {k}] {a:6.1f}-{b:6.1f}s {len(cs):3d}字  {''.join(c[0] for c in cs)[:40]}",
          flush=True)

htext = "".join(c[0] for c in hyp)
print(f"[hyp] {len(hyp)} 字 / {total:.1f}s")

# ---------- 全局对齐 ----------
pairs = align(ref, htext)
exact = [(r, h) for r, h in pairs if ref[r] == htext[h]]
print(f"[align] 对子 {len(pairs)}（全同 {len(exact)}）")

anchors, weak = {}, {}
for r, h in pairs:
    ch, s, e = hyp[h]
    if ref[r] == ch:
        anchors[r] = (s, e, True)
    else:
        weak.setdefault(r, (s, e, False))
for r, v in weak.items():
    anchors.setdefault(r, v)
print(f"[align] 锚点 {len(anchors)}/{len(ref)} ({len(anchors)/max(1,len(ref))*100:.1f}%)")

# ---------- 每行时间 ----------
row_t = []
for (s, e) in line_spans:
    ts = [anchors[p] for p in range(s, e) if p in anchors]
    if ts:
        row_t.append([min(t[0] for t in ts), max(t[1] for t in ts),
                      sum(1 for t in ts if t[2]), e - s])
    else:
        row_t.append(None)

# 无锚点的行：在前后锚点之间线性插值
for i, rt in enumerate(row_t):
    if rt is not None:
        continue
    prev = next((row_t[j] for j in range(i - 1, -1, -1) if row_t[j]), None)
    nxt = next((row_t[j] for j in range(i + 1, len(row_t)) if row_t[j]), None)
    if prev and nxt:
        row_t[i] = [prev[1], nxt[0], 0, 0]
    elif prev:
        row_t[i] = [prev[1], prev[1] + 3000, 0, 0]
    elif nxt:
        row_t[i] = [max(0, nxt[0] - 3000), nxt[0], 0, 0]

# ---------- 强制单调 + 最小间隔 ----------
starts = [rt[0] / 1000.0 if rt else 0.0 for rt in row_t]
for i in range(1, len(starts)):
    if starts[i] < starts[i - 1] + MIN_GAP:
        starts[i] = starts[i - 1] + MIN_GAP
# 反向再压一次末尾（防止某行起点被推爆）
for i in range(len(starts) - 2, -1, -1):
    if starts[i + 1] < starts[i] + MIN_GAP:
        starts[i] = starts[i + 1] - MIN_GAP
starts = [max(0.0, s) for s in starts]

for i, rt in enumerate(row_t):
    if rt:
        rt[0] = int(starts[i] * 1000)
        rt[1] = int(max(rt[1], rt[0] + 800))


def ts2lrc(ms):
    ms = max(0, int(ms))
    return f"{ms//60000:02d}:{(ms%60000)//1000:02d}.{ms%1000//10:02d}"


out = [f"[{ts2lrc(rt[0])}]{ln}" for ln, rt in zip(lines, row_t) if rt]
open(out_lrc, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"[out] {out_lrc} ({len(out)} 行)")

print("\n 行  起      止      全同/总字  歌词")
for i, (ln, rt) in enumerate(zip(lines, row_t)):
    if not rt:
        print(f"  {i:3d}  —— 无锚点 ——                {ln}")
        continue
    flag = "  " if rt[2] == rt[3] else ("~ " if rt[2] else "插")
    print(f"{flag}{i:3d} {ts2lrc(rt[0]):>8} {ts2lrc(rt[1]):>8}  {rt[2]:>4}/{rt[3]:<4}  {ln}")

if report_json:
    json.dump({"lines": [{"i": i, "text": ln, "start_ms": rt[0], "end_ms": rt[1],
                          "exact": rt[2], "total": rt[3]}
                         for i, (ln, rt) in enumerate(zip(lines, row_t)) if rt]},
              open(report_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
