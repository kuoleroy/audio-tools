# -*- coding: utf-8 -*-
"""lrc_core 的自检：python test_core.py（无依赖，秒级）。

只钉住真正会错的地方：编辑距离对不对得上、错字能不能挂上时间、连续缺锚点会不会塌。
"""
from lrc_core import (align, anchors_from, row_times, pad_missing, ts2lrc,
                      summarize, read_lyrics)


def test_align_basic():
    # 起↔妻 是错字替换，必须能配对并且单调递增
    pairs = align("妻死我鼓盆", "起死我鼓盆")
    assert [r for r, _ in pairs] == [0, 1, 2, 3, 4], pairs
    assert pairs[0] == (0, 0)


def test_align_deletion():
    # hyp 少一个字：对齐要跳过它，后面的字不能整体错位
    pairs = dict(align("abcd", "abd"))
    assert pairs[3] == 2, pairs          # 'd' 对到 hyp 的 'd'


def test_anchors_and_rows():
    ref, hyp = "ab", "xb"                # 第一字是错字，第二字相同
    times = [(0, 100), (100, 200)]
    a = anchors_from(ref, hyp, times, align(ref, hyp))
    assert a == {0: (0, 100, False), 1: (100, 200, True)}, a
    rt = row_times([(0, 1), (1, 2)], a, exact_only=True)
    assert rt[0] == [0, 100, 0, 1], rt      # 只有替换匹配 → 全同计数为 0
    assert rt[1] == [100, 200, 1, 1], rt


def test_pad_missing_no_collapse():
    # 中间连续两行缺锚点：在 [a.end, b.start] 里等分，不能塌成零长度、也不能挤在同一点
    row_t = [[0, 1000, 1, 1], None, None, [9000, 10000, 1, 1]]
    pad_missing(row_t)
    assert row_t[1] == [1000, 5000, 0, 0], row_t
    assert row_t[2] == [5000, 9000, 0, 0], row_t


def test_pad_missing_single_gap():
    # 单行缺口：整段铺满
    row_t = [[0, 1000, 1, 1], None, [9000, 10000, 1, 1]]
    pad_missing(row_t)
    assert row_t[1] == [1000, 9000, 0, 0], row_t


def test_ts2lrc():
    assert ts2lrc(0) == "00:00.00"
    assert ts2lrc(61123) == "01:01.12"
    assert ts2lrc(-5) == "00:00.00"


def test_summarize_counts_zero_total_as_guess():
    # 0/0 行是整行没锚点，不能因为 0==0 被算成「整行对上」
    row_t = [[0, 100, 3, 3], [0, 100, 1, 3], [0, 100, 0, 0]]
    assert summarize(row_t) == (1, 1, 1)


def test_read_lyrics_skips_section_markers():
    import tempfile, os
    p = os.path.join(tempfile.mkdtemp(), "l.txt")
    open(p, "w", encoding="utf-8").write("[Verse]\n第一句\n\n[Chorus]\n第二句\n")
    lines, ref, spans = read_lyrics(p)
    assert lines == ["第一句", "第二句"], lines      # 小节标记不能混进 ref
    assert "".join(ref) == "第一句第二句", ref
    assert spans == [(0, 3), (3, 6)], spans


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("\n全部通过")
