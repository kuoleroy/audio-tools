# -*- coding: utf-8 -*-
"""把 Paraformer 的字级时间戳对齐到已知歌词，生成逐行 LRC。

**歌词文字一律来自你的 lyrics.txt，ASR 只提供时间戳。** 识别出来错字、漏字都不影响
输出文字——它只影响哪些字能挂上时间，挂不上的行按前后行插值。

原理：ASR 认出的字（hyp）和你手上的歌词（ref）做编辑距离对齐
（允许替换匹配——"起"对"妻"这种近似字也要能挂上时间戳），
对齐后的对子直接搬时间戳；没挂上的行按前后行插值。

改完歌词想重对一次，不用重跑识别，直接再跑本脚本即可（秒级）。

用法: python align_lrc.py <asr.json> <lyrics.txt> <out.lrc> [report.json]
"""
import sys, json
from lrc_core import (read_lyrics, align, anchors_from, row_times, pad_missing, enforce_min_duration,
                      ts2lrc, summarize, dump_report, print_table)

asr_json, lyric_txt, out_lrc = sys.argv[1], sys.argv[2], sys.argv[3]
report_json = sys.argv[4] if len(sys.argv) > 4 else None

# ---------- 读 ASR 结果 ----------
res = json.load(open(asr_json, encoding="utf-8"))
if isinstance(res, dict):          # asr_chunked.py 的格式：单个 dict
    res = [res]

hyp, htimes = [], []
for seg in res:
    txt = seg.get("text", "") or ""
    ts = seg.get("timestamp") or []
    # text 里字之间可能有空格，时间戳是一字一条 —— 只能按「非空格字符」计数
    k = 0
    for ch in txt:
        if ch.isspace():
            continue
        hyp.append(ch)
        htimes.append(tuple(ts[k]) if k < len(ts) else None)
        k += 1
print(f"[hyp] {len(hyp)} 字, 有时间戳 {sum(1 for t in htimes if t)}")

lines, ref, spans = read_lyrics(lyric_txt)
print(f"[ref] {len(lines)} 行 / {len(ref)} 字")

pairs = align(ref, hyp)
print(f"[align] 对子 {len(pairs)}（其中完全相同 {sum(1 for r, h in pairs if ref[r] == hyp[h])}）")

anchors = anchors_from(ref, hyp, htimes, pairs)
print(f"[align] 锚点 {len(anchors)} / {len(ref)} 字 ({len(anchors) / max(1, len(ref)) * 100:.1f}%)")

row_t = enforce_min_duration(pad_missing(row_times(spans, anchors)))

out = [f"[{ts2lrc(rt[0])}]{ln}" for ln, rt in zip(lines, row_t) if rt]
open(out_lrc, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"[out] {out_lrc}  ({len(out)} 行)")

summarize(row_t)
print_table(lines, row_t)
if report_json:
    dump_report(report_json, lines, row_t, coverage=len(anchors) / max(1, len(ref)))
