# 音频 / 歌词工具集

本地跑的歌曲相关流水线：人声分离、ASR 对轴、歌词排版（ASS/LRC）、ComfyUI 出图。

全部离线运行，不调云服务。

---

## 脚本

| 文件 | 作用 |
|---|---|
| `asr_run.py` / `asr_chunked.py` | FunASR（Paraformer-large + FSMN-VAD）转写，出字级时间戳；chunked 版按段切分，长歌内存友好 |
| `vad_segments.py` | 只用 VAD 切句，不做识别 |
| `align_lrc.py` | **核心**：ASR 字级时间戳做编辑距离对齐到**你手上的准确歌词**，生成逐行 LRC。允许替换匹配（"起"对"妻"这类错字也能挂上时间戳），没挂上的行按前后插值 |
| `make_lrc.py` | 生成 LRC |
| `make_workflow.py` / `make_workflow_card.py` | 生成 ComfyUI 工作流 JSON / 卡片 |
| `comfy_t2i.py` | 走 ComfyUI 的 `/prompt` API 直接出图（Qwen-Image 2.1），不手点界面 |
| `full_gen.py` | 整条出图流水线 |
| `test_*.py` | 试音色、试 ACE、小样测试 |

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
