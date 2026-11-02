# -*- coding: utf-8 -*-
"""对轴向导：① 给音频 → 识别并记住每个字的时间；② 给歌词 txt → 出 LRC。

歌词文字一律来自你的 txt，识别只提供时间戳（识别错字不会进到歌词里）。

同一个音频第二次跑会直接复用 `<歌名>.asr.json`，跳过识别——所以改完歌词重对是秒级的事。
想重新识别，把那个 `.asr.json` 删掉再跑。

用法:
    python dui.py                # 全问答
    python dui.py 歌.wav         # 音频先给，只问歌词
"""
import os, sys
from lrc_core import (read_lyrics, transcribe, save_asr, load_asr, align,
                      anchors_from, row_times, pad_missing, ts2lrc,
                      summarize, print_table)

MODELS = os.environ.get(
    "ASR_MODELS", r"C:\Users\admin\AppData\Local\Comfy-Desktop\ComfyUI-Shared\models\asr")


def ask_file(prompt):
    """拖进终端的路径带引号和空格，清掉；打错了就重问，不抛异常。"""
    while True:
        p = input(prompt).strip().strip('"').strip("'").strip()
        if not p:
            print("  （没输入，Ctrl+C 退出）")
        elif not os.path.isfile(p):
            print(f"  找不到：{p}\n  把文件直接拖进这个窗口，或者粘贴完整路径。")
        else:
            return os.path.abspath(p)


def main():
    audio = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    if audio and not os.path.isfile(audio):
        print(f"找不到：{audio}")
        return
    if not audio:
        print("=" * 60)
        print("第一步：识别。给一次音频，之后这首歌就不用再识别了。")
        print("=" * 60)
        audio = ask_file("① 把歌曲拖进来（wav / flac / mp3）：")

    stem = os.path.splitext(audio)[0]
    asr_json = stem + ".asr.json"

    if os.path.isfile(asr_json):
        print(f"[asr] 复用已有识别：{asr_json}")
        print("      （想重新识别就把这个文件删掉，再跑一次本脚本）")
        hyp, htimes = load_asr(asr_json)
    else:
        print(f"[音频] {audio}")
        hyp, htimes, total = transcribe(audio, MODELS)
        save_asr(asr_json, hyp, htimes, os.path.basename(audio))
        print(f"[asr] 已存 {asr_json}")

    print(f"[hyp] 识别到 {len(hyp)} 字：{''.join(hyp[:40])}……")
    print()
    print("=" * 60)
    print("第二步：对轴。歌词一行一句，标点随便写，[Verse] 这类标记会自动跳过。")
    print("=" * 60)
    lyric = ask_file("② 把歌词 txt 拖进来：")

    lines, ref, spans = read_lyrics(lyric)
    print(f"[ref] {len(lines)} 行 / {len(ref)} 字")

    pairs = align(ref, hyp)
    anchors = anchors_from(ref, hyp, htimes, pairs)
    print(f"[align] 锚点 {len(anchors)}/{len(ref)} ({len(anchors) / max(1, len(ref)) * 100:.1f}%)")

    row_t = pad_missing(row_times(spans, anchors))
    out_lrc = stem + ".lrc"
    open(out_lrc, "w", encoding="utf-8").write(
        "\n".join(f"[{ts2lrc(rt[0])}]{ln}" for ln, rt in zip(lines, row_t) if rt) + "\n")

    print(f"\n[out] {out_lrc}")
    summarize(row_t)
    print_table(lines, row_t)
    print(f"\n改完歌词只再跑这一步就行：python dui.py \"{audio}\"")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
