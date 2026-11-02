# -*- coding: utf-8 -*-
"""把 Paraformer 的字级时间戳对齐到已知歌词，生成逐行 LRC。

原理：ASR 认出的字（hyp）和我们手上的歌词（ref）做编辑距离对齐
（允许替换匹配——"起"对"妻"这种近似字也要能挂上时间戳），
对齐后的对子直接搬时间戳；没挂上的行按前后行插值。

唱歌识别会错字，但只要大部分字能对齐上，逐行时间就够准。

用法: python align_lrc.py <asr.json> <lyrics.txt> <out.lrc> [report.json]
"""
import sys, json, re

asr_json, lyric_txt, out_lrc = sys.argv[1], sys.argv[2], sys.argv[3]
report_json = sys.argv[4] if len(sys.argv) > 4 else None

# ---------- 读 ASR 结果 ----------
res = json.load(open(asr_json, encoding="utf-8"))
if isinstance(res, dict):          # asr_chunked.py 的格式：单个 dict
    res = [res]

hyp_chars, hyp_times = [], []
for seg in res:
    txt = seg.get("text", "") or ""
    ts = seg.get("timestamp") or []
    # 注意：text 里字之间可能有空格，时间戳是一字一条 —— 只能按「非空格字符」计数
    k = 0
    for ch in txt:
        if ch.isspace():
            continue
        hyp_chars.append(ch)
        hyp_times.append(ts[k] if k < len(ts) else None)
        k += 1
print(f"[hyp] {len(hyp_chars)} 字, 有时间戳 {sum(1 for t in hyp_times if t)}")

# ---------- 读歌词 ----------
lines = []
for ln in open(lyric_txt, encoding="utf-8").read().splitlines():
    ln = ln.strip()
    if ln:
        lines.append(ln)

ref_chars, line_spans = [], []
for ln in lines:
    s = len(ref_chars)
    for ch in ln:
        if ch.isspace():
            continue
        ref_chars.append(ch)
    line_spans.append((s, len(ref_chars)))
print(f"[ref] {len(lines)} 行 / {len(ref_chars)} 字")


# ---------- 编辑距离对齐（带回溯），返回 (ref_idx, hyp_idx) 对子 ----------
def align(ref, hyp):
    n, m = len(ref), len(hyp)
    # dp[i][j] = ref[:i] 与 hyp[:j] 的最小编辑距离
    prev = list(range(m + 1))
    rows = [prev]
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        ri = ref[i - 1]
        for j in range(1, m + 1):
            cost = 0 if ri == hyp[j - 1] else 1     # 替换代价 1，等于就免费
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        rows.append(cur)
        prev = cur
    # 回溯
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        ri, hj = ref[i - 1], hyp[j - 1]
        cost = 0 if ri == hj else 1
        if rows[i][j] == rows[i - 1][j - 1] + cost:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif rows[i][j] == rows[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


pairs = align(ref_chars, hyp_chars)
exact = sum(1 for r, h in pairs if ref_chars[r] == hyp_chars[h])
print(f"[align] 对子 {len(pairs)}（其中完全相同 {exact}）")

# 搬时间戳：优先用完全相同的对子，其次用替换对子
anchors, weak = {}, {}
for r, h in pairs:
    t = hyp_times[h]
    if t is None:
        continue
    if ref_chars[r] == hyp_chars[h]:
        anchors[r] = t
    elif r not in anchors:
        weak[r] = t
anchors.update({r: t for r, t in weak.items() if r not in anchors})
print(f"[align] 锚点 {len(anchors)} / {len(ref_chars)} 字 "
      f"({len(anchors)/max(1,len(ref_chars))*100:.1f}%)")

# ---------- 每行取时间 ----------
row_t = []
for (s, e) in line_spans:
    ts = [anchors[p] for p in range(s, e) if p in anchors]
    if ts:
        row_t.append((min(t[0] for t in ts), max(t[1] for t in ts), len(ts), e - s))
    else:
        row_t.append(None)

# 未匹配上的行：按前后锚点插值
for i, rt in enumerate(row_t):
    if rt is not None:
        continue
    prev = next((row_t[j] for j in range(i - 1, -1, -1) if row_t[j]), None)
    nxt = next((row_t[j] for j in range(i + 1, len(row_t)) if row_t[j]), None)
    if prev and nxt:
        row_t[i] = (prev[1], nxt[0], 0, 0)
    elif prev:
        row_t[i] = (prev[1], prev[1] + 3000, 0, 0)
    elif nxt:
        row_t[i] = (max(0, nxt[0] - 3000), nxt[0], 0, 0)


def ts2lrc(ms):
    ms = max(0, int(ms))
    return f"{ms//60000:02d}:{(ms%60000)//1000:02d}.{ms%1000//10:02d}"


out = []
for i, (ln, rt) in enumerate(zip(lines, row_t)):
    if rt is None:
        continue
    out.append(f"[{ts2lrc(rt[0])}]{ln}")
open(out_lrc, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"[out] {out_lrc}  ({len(out)} 行)")

# ---------- 报告 ----------
print("\n 行  起      止      命中/总字  歌词")
for i, (ln, rt) in enumerate(zip(lines, row_t)):
    if rt is None:
        continue
    hit = f"{rt[2]}/{rt[3]}"
    flag = "  " if rt[2] == rt[3] else ("~ " if rt[2] else "插")
    print(f"{flag}{i:3d} {ts2lrc(rt[0]):>8} {ts2lrc(rt[1]):>8}  {hit:>8}  {ln}")

if report_json:
    json.dump({
        "lines": [{"i": i, "text": ln, "start_ms": rt[0], "end_ms": rt[1],
                   "hit": rt[2], "total": rt[3]} for i, (ln, rt) in enumerate(zip(lines, row_t)) if rt],
        "coverage": len(anchors) / max(1, len(ref_chars)),
    }, open(report_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[report]", report_json)
