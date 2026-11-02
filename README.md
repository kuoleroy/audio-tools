# 音频 / 歌词工具集

本地跑的歌曲相关流水线：人声分离、ASR 对轴、歌词排版（ASS/LRC）、ComfyUI 出图。

全部离线运行，不调云服务。

## 核心前提：歌词文本是准的，ASR 只负责给时间

识别人声一定会错字、漏字、把"妻"听成"起"。所以这套工具**不拿识别结果当歌词**——
输出里的每一个字、每一行都原样来自你手写的 `lyrics.txt`，ASR 提供的只有时间戳。
识别错了只会让某几个字挂不上时间，绝不会改掉你的词。

## 怎么用（问答式）

```bash
python dui.py
```

跑起来就两句问话，把文件拖进窗口即可：

```
① 把歌曲拖进来（wav / flac / mp3）：D:\歌\相交线.wav
   → 分块识别，把每个字的时间存成 相交线.asr.json   （约 45 秒 / 3.5 分钟的歌）
② 把歌词 txt 拖进来：D:\歌\lyrics.txt
   → 出 相交线.lrc
```

**识别只能跑一次。** 再跑同一首歌会自动复用 `相交线.asr.json`，只做对齐——改错字、
拆句、删句、重排，都是秒级重出 LRC。想重新识别，把那个 `.asr.json` 删掉再跑。

产物落在音频旁边：`相交线.asr.json`（时间戳底料）、`相交线.lrc`（成品）。

### 命令行等价写法

```bash
# 识别 + 对轴一次做完，并把识别结果存下来
python make_lrc.py 歌.flac lyrics.txt out.lrc report.json out.asr.json

# 之后改歌词只跑这个
python align_lrc.py out.asr.json lyrics.txt out.lrc
```

跑完会打一行 `[quality]` 告诉你多少行是真对上的、多少行是插值猜的：

```
[quality] 整行对上 26 / 部分对上 3 / 全靠插值 3（共 32 行，81% 可靠）
```

`[quality]` 统计的是「这行时间可不可信」，不是「识别准不准」。**全是插值的那几行
在下面的表里标 `插`，时间基本是猜的，需要你手工改。**

唱腔比说话难识别，Paraformer 会整句漏掉。可靠度低时按这个顺序查：① 输入必须是
**人声分离后的 vocals**，混音会被伴奏带偏；② 已经是 vocals 还低，就换更强的声学
模型（SenseVoice / Whisper）重跑识别，或手工校正那几行。

注意 LRC 的时间是相对**你喂进去的那个音频文件**的。识别用的文件必须和最终播放/合成
用的是同一条，否则整条时间轴会一起偏移（比如干声开头有 40 秒前奏，第一句就会落在
`[00:40.03]`）。

---

## 脚本

| 文件 | 作用 |
|---|---|
| `dui.py` | **问答式主入口**。给音频→识别存时间戳；给歌词→出 LRC。同一首歌第二次跑自动跳过识别 |
| `lrc_core.py` | **核心零件**：分块识别、读歌词、编辑距离对齐、锚点、逐行取时、缺口插值、LRC 时间。下面几个脚本共用 |
| `make_lrc.py` | 命令行版：识别 + 对齐 + 强制单调间隔一次做完 |
| `align_lrc.py` | 只做对齐：拿已有 asr.json 和你的歌词出 LRC。改完歌词秒出 |
| `asr_run.py` / `asr_chunked.py` | 只跑识别，出字级时间戳 JSON；chunked 版带重叠合并，适合长音频 |
| `vad_segments.py` | 只用 VAD 切句，不做识别 |
| `test_core.py` | `lrc_core` 自检，无依赖秒级：`python test_core.py` |
| `make_workflow.py` / `make_workflow_card.py` | 生成 ComfyUI 界面用的工作流 JSON / 卡片 |
| `comfy_t2i.py` | 走 ComfyUI 的 `/prompt` API 直接出图（Qwen-Image 2.1），不手点界面 |
| `full_gen.py` | 整条出歌流水线（ACE-Step 1.5） |

模型路径可用环境变量覆盖：`set ASR_MODELS=D:\models\asr`（默认指向本机 ComfyUI 共享目录）。

## `lrc/` — 歌词工程

```
lrc/
├── lyrics_xjl.txt          准确歌词（人工校对过的）
├── asr_xjl*.json           ASR 结果（字级时间戳）
├── vad_xjl.json            VAD 切句
├── xiangjielian_16k.wav    16k 单声道，ASR 用
├── vocals_16k.wav          分离后人声，识别准确率更高
└── fz/                     歌词排版（12 种 ASS 样式）
    ├── _style_*.ass
    └── report_fz.json      逐行对齐报告
```

### 12 种 ASS 歌词样式

| 样式 | 特征 |
|---|---|
| **`grid`** | **楷体 60，居中，104px 行距 × 6 行，累积满页翻页复位**。唱过的句子保留，正在唱的行琥珀橙 3C6AE8 高亮 |
| `grid-industrial` | 雅黑 Bold 54，左对齐，92px 行距，每行一根橙色竖条，累积持续下压（不翻页）|
| `cine` | 电影字幕感，`\move` 位移 |
| `fadeup` | 淡入上浮 + 118% 缩放 |
| `huge` | 巨字 158% 放大 |
| `slam` | 砸落，130% → 105% 回弹 |
| `blur` | 106% 缩放 + 模糊 |
| `neon` | 霓虹描边 |
| `ink` | 墨迹感 |
| `mirror` | 镜像 |
| `type` | 打字机 |
| `vtext` | 竖排 |

画布统一 1080×1920（竖屏 MV）。

---

## 依赖

脚本依赖：`funasr`、`torch`、`audio-separator`、`safetensors`、`ffmpeg`（命令行）。

**不要用 `pip install --target` 把包装进本目录**——那样包会散成一堆目录，且必须改 `PYTHONPATH` 才能 import，属于不可维护状态。必须建 venv。

已就绪的环境（本机）：

```
C:\Users\admin\.venvs\audio-sep\Scripts\python.exe     # Python 3.13 + torch 2.14.1+cu126 (CUDA True)
```

已装：`funasr`（Paraformer + FSMN-VAD）、`audio-separator 0.48.0`（UVR，含 htdemucs / MDX / VR 系模型）、`soundfile`、`numpy`。

重装的话：

```bash
python -m venv venv
venv/Scripts/python.exe -m pip install -U pip
venv/Scripts/python.exe -m pip install funasr audio-separator soundfile
# torch 按显卡选 cu126，注意 torch 与 torchaudio 版本要配套
venv/Scripts/python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

### 人声分离

不用 `demucs` 这个包（它跟新版 torch 的 torchaudio 对不上），用 `audio-separator`：

```bash
audio-separator song.flac \
  --model_filename htdemucs_ft.yaml \
  --model_file_dir C:/Users/admin/audio-models \
  --output_dir out --output_format FLAC
```

权重在 `C:\Users\admin\audio-models`（htdemucs_ft 四轨：vocals / drums / bass / other，约 377 MB）。
同目录下 `分离-拖文件到这里.bat` 是拖拽入口。

---

## 不该入库的东西

`.gitignore` 已排除：

| 排除 | 原因 |
|---|---|
| `sep/`（320 MB） | demucs 分离出的分轨，属音频素材，体积大且涉版权 |
| `lrc/*.wav`、`lrc/sep/`、`lrc/chk/`、`lrc/t/` | 同上 |
| `lrc/fz/out/` | 渲染产物 |
| `tmp/`、`montage/` | 中间件 |
| `venv/`、`__pycache__/` | 环境 |

**入库的只有：脚本 + 样式文件 + 校对过的歌词 + 对齐报告。**

---

## 许可证

代码以 **MIT** 协议开源，见 [`LICENSE`](LICENSE)。

例外：`lrc/` 下的歌词文本（`lyrics*.txt`、各 `.ass` 样式里的句子）是原创词作《相交线》，随仓库公开仅为演示排版效果。翻唱、改编、商用请先联系作者。

第三方依赖各自遵循其协议：`funasr`（MIT）、`audio-separator`（MIT）、`torch`（BSD-3-Clause）、`PySide6` 等见各自仓库。
