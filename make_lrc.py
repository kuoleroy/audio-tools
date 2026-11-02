# -*- coding: utf-8 -*-
"""直接出 LRC：分块识别 → 全局对齐歌词 → 逐行时间（单调、不倒流）。

**歌词文字一律来自你的 lyrics.txt，ASR 只提供时间戳**（识别错字不影响输出文字）。

要点：
- 长音频整跑会崩（CIF 累积误差），必须切块（≤20s）逐块识别；
- 切块不重叠，避免同一段被认两遍导致文字互相打架；
- 全文与歌词做编辑距离对齐（允许替换匹配：起↔妻、道行↔舞蹈），
  对上的字搬时间戳；认不出的行按前后锚点插值；
- 最后强制单调：行与行之间时间不倒流、间隔不小于 1 秒。

输入用**人声分离后的 vocals**，不要用混音——伴奏会把识别带偏，锚点覆盖率会掉一半。
格式随意（wav / flac / mp3），内部统一转 16k 单声道。

用法: python make_lrc.py <vocals 音频> <lyrics.txt> <out.lrc> [report.json]
"""
import sys, os, subprocess, tempfile
import numpy as np
from lrc_core import (read_lyrics, align, anchors_from, row_times, pad_missing,
                      ts2lrc, summarize, dump_report, print_table)

wav_path, lyric_txt, out_lrc = sys.argv[1], sys.argv[2], sys.argv[3]
report_json = sys.argv[4] if len(sys.argv) > 4 else None

MODELS = os.environ.get(
    "ASR_MODELS", r"C:\Users\admin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\asr")
ASR_DIR = os.path.join(MODELS, "paraformer-large_asr_nat-zh-cn-16k-common-vocab8404")
VAD_DIR = os.path.join(MODELS, "fsmn-vad_zh-cn-16k-common")

CHUNK = 20.0          # 块长；块与块不重叠
MIN_GAP = 1.0         # 相邻两行最小间隔（秒）

lines, ref, spans = read_lyrics(lyric_txt)
print(f"[ref] {len(lines)} 行 / {len(ref)} 字")

# ---------- 能量包络 → 安静切点 ----------
# ponytail: 用 ffmpeg 解码成 16k 单声道比 wave 模块短，还能吃 flac/mp3（分离出来的就是 flac）
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", wav_path,
                      "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                     capture_output=True, check=True).stdout
audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
sr = 16000
total = len(audio) / sr
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
print(f"[plan] {len(bounds) - 1} 块（不重叠）")

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
                cs.append((ch, (ts[j][0] + a * 1000, ts[j][1] + a * 1000)))
            j += 1
    for ch, t in cs:
        hyp.append(ch)
        htimes.append(t)
    print(f"[chunk {k}] {a:6.1f}-{b:6.1f}s {len(cs):3d}字  {''.join(c[0] for c in cs)[:40]}",
          flush=True)

print(f"[hyp] {len(hyp)} 字 / {total:.1f}s")

# ---------- 全局对齐 ----------
pairs = align(ref, hyp)
print(f"[align] 对子 {len(pairs)}（全同 {sum(1 for r, h in pairs if ref[r] == hyp[h])}）")

anchors = anchors_from(ref, hyp, htimes, pairs)
print(f"[align] 锚点 {len(anchors)}/{len(ref)} ({len(anchors) / max(1, len(ref)) * 100:.1f}%)")

row_t = pad_missing(row_times(spans, anchors, exact_only=True))

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

out = [f"[{ts2lrc(rt[0])}]{ln}" for ln, rt in zip(lines, row_t) if rt]
open(out_lrc, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"[out] {out_lrc} ({len(out)} 行)")

summarize(row_t)
print_table(lines, row_t)
if report_json:
    dump_report(report_json, lines, row_t)
