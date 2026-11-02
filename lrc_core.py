# -*- coding: utf-8 -*-
"""align_lrc.py / make_lrc.py 共用的部分：读歌词、编辑距离对齐、锚点、逐行取时、插值、LRC 时间。

这两个脚本原先各存了一份拷贝（连 anchor 的两段式去重都抄了），改一处得改两处。
"""
from bisect import bisect_left


def read_lyrics(path):
    """→ (lines, ref_chars, line_spans)；ref 只留非空白字，spans 是每行在 ref 里的下标区间"""
    lines = [ln.strip() for ln in open(path, encoding="utf-8").read().splitlines() if ln.strip()]
    ref, spans = [], []
    for ln in lines:
        s = len(ref)
        ref.extend(ch for ch in ln if not ch.isspace())
        spans.append((s, len(ref)))
    return lines, ref, spans


def align(ref, hyp):
    """编辑距离对齐（替换代价 1），回溯返回单调递增的 (ref_idx, hyp_idx) 对子。
    ref / hyp 只要可按下标取字符即可（str 或 list）。"""
    n, m = len(ref), len(hyp)
    rows = [list(range(m + 1))]
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        ri, prev = ref[i - 1], rows[-1]
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (0 if ri == hyp[j - 1] else 1))
        rows.append(cur)
    pairs, i, j = [], n, m
    while i > 0 and j > 0:
        cur = rows[i][j]
        if cur == rows[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif cur == rows[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def anchors_from(ref, hyp, times, pairs):
    """pairs → {ref_idx: (start_ms, end_ms, 是否完全同字)}；times[i] 为 None 的对子丢掉。
    回溯是对角走的，ref 下标天然不重复，所以不需要「精确优先、替换兜底」两段式去重。"""
    return {r: (times[h][0], times[h][1], ref[r] == hyp[h])
            for r, h in pairs if times[h]}


def row_times(spans, anchors, exact_only=False):
    """每行取 [起, 止, 命中字数, 总字数]；一个字都没锚上的行给 None。
    exact_only=True 时命中只数完全同字的（make_lrc 的「全同」口径）。"""
    out = []
    for s, e in spans:
        hit = [anchors[p] for p in range(s, e) if p in anchors]
        if not hit:
            out.append(None)
            continue
        n = sum(t[2] for t in hit) if exact_only else len(hit)
        out.append([min(t[0] for t in hit), max(t[1] for t in hit), n, e - s])
    return out


def pad_missing(row_t, fallback_ms=3000):
    """没锚点的行在前后行之间等分铺开；首尾缺失就往外推 fallback_ms。原地改。

    两个坑：① 前后锚点只从「本来就有锚点」的行里找，否则刚填好的行会被当成下一行的前锚点，
    连续多行缺失时一路塌成零长度；② 连续多行缺口不能都塞在边界点上，
    否则几句歌词会同时出现（三句全在 0:01.15 这样）。"""
    known = [i for i, rt in enumerate(row_t) if rt]
    i = 0
    while i < len(row_t):
        if row_t[i] is not None:
            i += 1
            continue
        j = i
        while j < len(row_t) and row_t[j] is None:
            j += 1
        k = bisect_left(known, i)
        prev = row_t[known[k - 1]] if k else None
        nxt = row_t[known[k]] if k < len(known) else None
        a = prev[1] if prev else (max(0, nxt[0] - fallback_ms) if nxt else 0)
        b = nxt[0] if nxt else a + fallback_ms * (j - i)
        step = (b - a) / (j - i)
        for t in range(i, j):
            row_t[t] = [int(a + step * (t - i)), int(a + step * (t - i + 1)), 0, 0]
        i = j
    return row_t


def ts2lrc(ms):
    ms = max(0, int(ms))
    return f"{ms // 60000:02d}:{(ms % 60000) // 1000:02d}.{ms % 1000 // 10:02d}"


def dump_report(path, lines, row_t, **extra):
    import json
    json.dump({"lines": [{"i": i, "text": ln, "start_ms": rt[0], "end_ms": rt[1],
                          "hit": rt[2], "total": rt[3]}
                         for i, (ln, rt) in enumerate(zip(lines, row_t)) if rt],
               **extra},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n[report]", path)


def print_table(lines, row_t):
    print("\n 行  起      止      命中/总字  歌词")
    for i, (ln, rt) in enumerate(zip(lines, row_t)):
        if rt is None:
            print(f"  {i:3d}  —— 无锚点 ——                {ln}")
            continue
        flag = "  " if rt[2] == rt[3] else ("~ " if rt[2] else "插")
        print(f"{flag}{i:3d} {ts2lrc(rt[0]):>8} {ts2lrc(rt[1]):>8}  "
              f"{rt[2]:>4}/{rt[3]:<4}  {ln}")
