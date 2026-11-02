# -*- coding: utf-8 -*-
"""lrc_core 的自检：python test_core.py（无依赖，秒级）。

只钉住真正会错的地方：编辑距离对不对得上、错字能不能挂上时间、连续缺锚点会不会塌。
"""
from lrc_core import align, anchors_from, row_times, pad_missing, ts2lrc


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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
    print("\n全部通过")
