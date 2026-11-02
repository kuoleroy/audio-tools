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

只想问答式操作就用 `dui.py`，这个脚本是它的命令行版。

用法: python make_lrc.py <vocals 音频> <lyrics.txt> <out.lrc> [report.json] [asr.json]

给了 asr.json 就把识别结果存下来——以后改歌词只需 align_lrc.py 秒级重对，不用再识别。
"""
import sys, os
from lrc_core import (read_lyrics, transcribe, save_asr, align, anchors_from,
                      row_times, pad_missing, ts2lrc, summarize, dump_report, print_table)

wav_path, lyric_txt, out_lrc = sys.argv[1], sys.argv[2], sys.argv[3]
report_json = sys.argv[4] if len(sys.argv) > 4 else None
asr_json = sys.argv[5] if len(sys.argv) > 5 else None

MODELS = os.environ.get(
    "ASR_MODELS", r"C:\Users\admin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\asr")
CHUNK = 20.0          # 块长；块与块不重叠
MIN_GAP = 1.0         # 相邻两行最小间隔（秒）

lines, ref, spans = read_lyrics(lyric_txt)
print(f"[ref] {len(lines)} 行 / {len(ref)} 字")

hyp, htimes, total = transcribe(wav_path, MODELS, CHUNK)
if asr_json:
    save_asr(asr_json, hyp, htimes, os.path.basename(wav_path))
    print(f"[asr] {asr_json}（以后重对用 align_lrc.py）")

# ---------- 全局对齐 ----------
pairs = align(ref, hyp)
print(f"[align] 对子 {len(pairs)}（全同 {sum(1 for r, h in pairs if ref[r] == hyp[h])}）")

anchors = anchors_from(ref, hyp, htimes, pairs)
print(f"[align] 锚点 {len(anchors)}/{len(ref)} ({len(anchors) / max(1, len(ref)) * 100:.1f}%)")

row_t = pad_missing(row_times(spans, anchors))

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
