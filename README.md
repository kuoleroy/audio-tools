# 歌词对轴工具

把**你手上准确的歌词文本**对到音频时间轴上，出 LRC。识别只负责给时间，不产出文字。

全部本地跑，不调云服务。

---

## 核心前提：歌词文本是准的，ASR 只负责给时间

识别人声一定会错字、漏字、把"妻"听成"起"。所以这套工具**不拿识别结果当歌词**——
输出里的每一个字、每一行都原样来自你手写的 `lyrics.txt`，ASR 提供的只有时间戳。
识别错了只会让某几个字挂不上时间，绝不会改掉你的词。

对齐用编辑距离：识别出的字（hyp）和你写的字（ref）做匹配，允许替换（"起"↔"妻"），
对上的字搬时间戳，没对上的行按前后行插值。

---

## 安装

```bash
python -m venv venv
venv/Scripts/python.exe -m pip install -U pip
venv/Scripts/python.exe -m pip install funasr soundfile numpy
# torch 按显卡选，cu126 为例
venv/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu126
```

还需要 `ffmpeg` 在 PATH 里（解码音频、切块都靠它）。

**不要用 `pip install --target` 把包装进本目录**——包会散成一堆目录，还得改 `PYTHONPATH`，不可维护。

### 两个环境变量

| 变量 | 指向 | 用途 |
|---|---|---|
| `ASR_MODELS` | 放 ASR 模型的目录 | 目录下需有 `paraformer-large_asr_nat-zh-cn-16k-common-vocab8404` 和 `fsmn-vad_zh-cn-16k-common` |
| `AUDIO_PY` | 装好 `funasr` 的那个 python | 可选。有它时，用别的 python 启动 `dui.py` 会自动切过去 |

```powershell
setx ASR_MODELS D:\models\asr
setx AUDIO_PY D:\venvs\audio\Scripts\python.exe    # 可选
```

```bash
export ASR_MODELS=~/models/asr
```

模型可从 [ModelScope](https://modelscope.cn/models/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch)
和 `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` 下载，放成上面那两个文件夹名即可。

---

## 怎么用

```bash
python dui.py
```

两句问话，把文件拖进窗口：

```
① 把歌曲拖进来（wav / flac / mp3）：D:\歌\vocals.wav
   → 分块识别，把每个字的时间存成 vocals.asr.json   （约 45 秒 / 3.5 分钟的歌）
② 把歌词 txt 拖进来：D:\歌\lyrics.txt
   → 出 vocals.lrc
```

**识别只能跑一次。** 再跑同一首歌会自动复用 `vocals.asr.json`，只做对齐——改错字、
拆句、删句、重排，都是秒级重出 LRC。想重新识别，把那个 `.asr.json` 删掉再跑。

产物落在音频旁边：`vocals.asr.json`（时间戳底料）、`vocals.lrc`（成品）。

### 命令行等价写法

```bash
# 识别 + 对轴一次做完，并把识别结果存下来
python make_lrc.py 歌.flac lyrics.txt out.lrc report.json out.asr.json

# 之后改歌词只跑这个
python align_lrc.py out.asr.json lyrics.txt out.lrc
```

### 输入音频

用**人声分离后的干声**，不要用混音——伴奏会把识别带偏，锚点覆盖率会掉一截。

---

## 输出怎么读

跑完会打一行 `[quality]`：

```
[quality] 稳 26 / 偏 7 / 插值 2（共 35 行）
          稳 = 该行 ≥80% 的字挂上了时间，能直接用；偏 = 有锚点但不够，时间可能差半句；插值 = 一个字没锚上，时间是我猜的
```

下面是逐行表，三种标记：

```
 行  起      止      命中/总字  歌词
    4 00:58.89 01:01.10     6/6     这一行整行都对上了
~   7 01:17.14 01:19.71     2/9     这一行只对上一部分，时间可能差半句
插  8 01:19.71 01:22.30     0/0     这一行一个字都没锚上，时间是我猜的
```

- 空着 = 稳，时间可信
- `~` = 偏，可能要微调半句
- `插` = 一个字都没锚上，**时间是我猜的，这几行得手改**

唱腔比说话难识别，Paraformer 会整句漏掉。`插` 的行多时按这个顺序查：
① 输入是不是分离后的 vocals；② 已经是 vocals 还多，就换更强的声学模型重跑识别
（SenseVoice / Whisper），或用[歌词滚动姬](https://lrc-maker.github.io)、Aegisub 手工改那几行。

注意 LRC 的时间是相对**你喂进去的那个音频文件**的。识别用的文件必须和最终播放/合成
用的是同一条，否则整条时间轴会一起偏移（干声开头有 40 秒前奏，第一句就落在 `[00:40.03]`）。

---

## 脚本

| 文件 | 作用 |
|---|---|
| `dui.py` | **问答式主入口**。给音频→识别存时间戳；给歌词→出 LRC。同一首歌第二次跑自动跳过识别 |
| `lrc_core.py` | **核心零件**：分块识别、读歌词、编辑距离对齐、锚点、逐行取时、缺口插值、补时长、LRC 时间。下面几个脚本共用 |
| `make_lrc.py` | 命令行版：识别 + 对齐 + 强制单调间隔一次做完 |
| `align_lrc.py` | 只做对齐：拿已有 asr.json 和你的歌词出 LRC。改完歌词秒出 |
| `asr_run.py` / `asr_chunked.py` | 只跑识别，出字级时间戳 JSON；chunked 版带重叠合并，长音频用 |
| `vad_segments.py` | 只用 VAD 切句，不做识别 |
| `test_core.py` | `lrc_core` 自检，无依赖秒级：`python test_core.py` |

---

## 人声分离

不用 `demucs` 这个包（跟新版 torch 的 torchaudio 版本对不上），用 `audio-separator`：

```bash
audio-separator song.flac \
  --model_filename htdemucs_ft.yaml \
  --model_file_dir ./models \
  --output_dir out --output_format FLAC
```

权重（htdemucs_ft 四轨：vocals / drums / bass / other）首次运行会自动下载到 `--model_file_dir`。

---

## 许可证

代码以 **MIT** 协议开源，见 [`LICENSE`](LICENSE)。

第三方依赖各自遵循其协议：`funasr`（MIT）、`torch`（BSD-3-Clause）。
