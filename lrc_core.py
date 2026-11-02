# -*- coding: utf-8 -*-
"""align_lrc.py / make_lrc.py 共用的部分：读歌词、编辑距离对齐、锚点、逐行取时、插值、LRC 时间。

这两个脚本原先各存了一份拷贝（连 anchor 的两段式去重都抄了），改一处得改两处。
"""
from bisect import bisect_left


def read_lyrics(path):
    """→ (lines, ref_chars, line_spans)；ref 只留非空白字，spans 是每行在 ref 里的下标区间。

    一行 = 一条字幕。`[Verse]` 这种小节标记不算歌词——不然它的字会混进 ref，
    把整段对齐往后推，导致后面每一行都错位。"""
    lines = [ln.strip() for ln in open(path, encoding="utf-8").read().splitlines()]
    lines = [ln for ln in lines if ln and not (ln.startswith("[") and ln.endswith("]"))]
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

    两种口径：默认「有锚点就算命中」——用来判断这行时间可不可信；
    exact_only=True 只数完全同字的——用来判断识别本身准不准。
    外面对用户报的可靠度一律用默认口径，别看错成识别准确率。"""
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


def enforce_min_duration(row_t, min_ms=800):
    """补足过短的行。原地改。

    LRC 的行靠「下一行的时间」收尾——两行时间一样时，前一行就是 0 时长，
    播放器里永远不会出现。歌词页实测会撞上这种情况（整行没锚点、后面又紧贴着下一句）。

    补法是往后借：把后续行的起点整体后移，借不动（已经是最后一行）就本行自己延长。
    借完仍然起点单调、行与行不重叠。"""
    n = len(row_t)
    for i in range(n):
        rt = row_t[i]
        if not rt or rt[1] - rt[0] >= min_ms:
            continue
        target = rt[0] + min_ms
        need = target                 # 下一行最早能开始的位置
        j = i + 1
        while j < n and row_t[j] and row_t[j][0] < need:
            shift = need - row_t[j][0]
            row_t[j][0] += shift
            row_t[j][1] += shift
            need = row_t[j][1]
            j += 1
        rt[1] = target
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


def models_dir():
    """ASR 模型目录（含 paraformer-large… 和 fsmn-vad…），由环境变量 ASR_MODELS 指定。

    不写死路径：这仓库是给别人 clone 的，默认值塞一个本机路径等于谁都跑不了。
    """
    import os
    p = os.environ.get("ASR_MODELS", "").strip()
    if not p:
        raise SystemExit(
            "[!] 没设 ASR_MODELS。指向放了模型的目录，例如：\n"
            "      Windows      setx ASR_MODELS D:\\models\\asr      （重开终端生效）\n"
            "      macOS/Linux  export ASR_MODELS=~/models/asr\n"
            "    目录下应有 paraformer-large_asr_nat-zh-cn-16k-common-vocab8404\n"
            "    和 fsmn-vad_zh-cn-16k-common 两个文件夹。")
    return p


def transcribe(audio_path, models_root, chunk=20.0):
    """分块跑 Paraformer，返回 (chars, times, total_seconds)。

    长音频整跑会崩（CIF 累积误差），所以切块；切点挑能量最低处，别从字中间切。
    funasr/numpy 在这里才 import，好让 test_core.py 不装它们也能跑。
    """
    import os, subprocess, tempfile
    import numpy as np
    from funasr import AutoModel

    asr_dir = os.path.join(models_root, "paraformer-large_asr_nat-zh-cn-16k-common-vocab8404")
    vad_dir = os.path.join(models_root, "fsmn-vad_zh-cn-16k-common")

    # ffmpeg 解码成 16k 单声道，比 wave 模块短，还能吃 flac/mp3（分离出来的就是 flac）
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", audio_path,
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
    while bounds[-1] + chunk < total - 1.0:
        nxt = quietest_at(min(bounds[-1] + chunk, total - 2.0))
        bounds.append(nxt if nxt > bounds[-1] + 8 else bounds[-1] + chunk)
    bounds.append(total)
    print(f"[plan] {len(bounds) - 1} 块（不重叠）")

    model = AutoModel(model=asr_dir, vad_model=vad_dir, device="cuda",
                      disable_update=True, disable_pbar=True)
    tmpdir = tempfile.mkdtemp(prefix="asr_")
    hyp, times = [], []
    for k in range(len(bounds) - 1):
        a, b = bounds[k], bounds[k + 1]
        if b - a < 1.0:
            continue
        seg = os.path.join(tmpdir, f"c{k}.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
                        "-i", audio_path, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", seg],
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
            times.append(t)
        print(f"[chunk {k}] {a:6.1f}-{b:6.1f}s {len(cs):3d}字  "
              f"{''.join(c[0] for c in cs)[:40]}", flush=True)

    print(f"[hyp] {len(hyp)} 字 / {total:.1f}s")
    return hyp, times, total


def save_asr(path, chars, times, key=""):
    import json
    json.dump({"key": key, "text": " ".join(chars),
               "timestamp": [[int(s), int(e)] for s, e in times]},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return path


def load_asr(path):
    """→ (chars, times)，给 align 用"""
    import json
    d = json.load(open(path, encoding="utf-8"))
    chars = [c for c in d["text"] if not c.isspace()]
    return chars, [tuple(t) for t in d["timestamp"]]


def summarize(row_t, good_ratio=0.8, warn_imputed=0.3):
    """按「这一行有多少字挂上了时间」分三档。

    别用「一行里一个字都不差」当及格线：11 个字对上 10 个，时间完全可用，
    按严口径会算成不可靠，报出来的数字低到吓人（实测 80% 锚点覆盖率 → 只有 23% 行全同）。"""
    rows = [rt for rt in row_t if rt]
    n = len(rows)
    solid = sum(1 for rt in rows if rt[3] and rt[2] / rt[3] >= good_ratio)
    imputed = sum(1 for rt in rows if not rt[2])
    weak = n - solid - imputed
    print(f"[quality] 稳 {solid} / 偏 {weak} / 插值 {imputed}（共 {n} 行）")
    print(f"          稳 = 该行 ≥{good_ratio:.0%} 的字挂上了时间，能直接用；"
          f"偏 = 有锚点但不够，时间可能差半句；插值 = 一个字没锚上，时间是我猜的")
    if n and imputed / n > warn_imputed:
        print(f"[warn] {imputed}/{n} 行全靠插值。按这两步查：\n"
              "  1) 输入必须是**分离后的 vocals**，混音直接识别会被伴奏带偏；\n"
              "  2) 已经是 vocals 还低，就是模型对唱腔不适应（唱歌比说话难识别），\n"
              "     换更强的声学模型（SenseVoice / Whisper）重跑识别，或手工校正插值行。")
    return solid, weak, imputed


def print_table(lines, row_t):
    print("\n 行  起      止      命中/总字  歌词")
    for i, (ln, rt) in enumerate(zip(lines, row_t)):
        if rt is None:
            print(f"  {i:3d}  —— 无锚点 ——                {ln}")
            continue
        flag = ("插" if not rt[2]
                else ("  " if rt[3] and rt[2] / rt[3] >= 0.8 else "~ "))
        print(f"{flag}{i:3d} {ts2lrc(rt[0]):>8} {ts2lrc(rt[1]):>8}  "
              f"{rt[2]:>4}/{rt[3]:<4}  {ln}")
