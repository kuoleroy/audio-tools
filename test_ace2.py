"""ACE-Step 1.5 正确配置测试：1.7B 编码器 + 两种模式

用法:
    python test_ace2.py 30 ace_v4_txt txt        # 纯文本驱动，audio codes 打开（官方默认）
    python test_ace2.py 30 ace_v4_ref ref_a_vox  # 参考音频驱动，codes 关闭（官方建议）
"""
import json
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:8188"

TAGS = ("industrial dub reggae, heavy sub bass, tape saturation, sparse drum machine, "
        "cavernous spring reverb, male gritty vocal, dark, 72 BPM")

LYRICS = """[Verse]
我们是两条相交线
相遇在流水线
还没来得及看清你的脸
就被齿轮的洪流冲散

[Chorus]
我们是两条相交线
相交一次 就再也回不来"""

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "ace_v4"
MODE = sys.argv[3] if len(sys.argv) > 3 else "txt"      # txt | ref | 参考音频文件名

# refon = 参考音频 + audio codes 同时开（官方没推荐，但质量更好，值得试）
USE_REF = MODE != "txt"
REF = MODE.replace("refon:", "") if USE_REF else None
CODES = MODE == "txt" or MODE.startswith("refon:")

WF = {
    "1": {"class_type": "UNETLoader",
          "inputs": {"unet_name": "acestep_v1.5_turbo.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "DualCLIPLoader",
          "inputs": {"clip_name1": "qwen_0.6b_ace15.safetensors",
                     "clip_name2": "qwen_1.7b_ace15.safetensors",
                     "type": "ace"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ace_1.5_vae.safetensors"}},
    "6": {"class_type": "TextEncodeAceStepAudio1.5",
          "inputs": {"clip": ["2", 0], "tags": TAGS, "lyrics": LYRICS,
                     "seed": 42, "bpm": 72, "duration": SECONDS,
                     "timesignature": "4", "language": "zh", "keyscale": "A minor",
                     "generate_audio_codes": CODES, "cfg_scale": 2.0,
                     "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
    "9": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
    "10": {"class_type": "KSampler",
           "inputs": {"model": ["9", 0], "seed": 42, "steps": 8, "cfg": 1.0,
                      "sampler_name": "euler", "scheduler": "simple",
                      "positive": ["7", 0], "negative": ["8", 0],
                      "latent_image": ["11", 0], "denoise": 1.0}},
    "11": {"class_type": "EmptyAceStep1.5LatentAudio",
           "inputs": {"seconds": SECONDS, "batch_size": 1}},
    "12": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
    "13": {"class_type": "SaveAudio", "inputs": {"audio": ["12", 0], "filename_prefix": PREFIX}},
}

if USE_REF:
    WF["4"] = {"class_type": "LoadAudio", "inputs": {"audio": REF}}
    WF["5"] = {"class_type": "VAEEncodeAudio", "inputs": {"audio": ["4", 0], "vae": ["3", 0]}}
    WF["7"] = {"class_type": "ReferenceTimbreAudio",
               "inputs": {"conditioning": ["6", 0], "latent": ["5", 0]}}
    WF["8"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}}
else:
    WF["7"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}}
    WF["8"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}}
    WF["10"]["inputs"]["positive"] = ["6", 0]


def get(path):
    return json.loads(urllib.request.urlopen(HOST + path, timeout=30).read())


def post(path, obj):
    req = urllib.request.Request(HOST + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        print("HTTP", e.code)
        print(e.read().decode("utf-8", "replace")[:3000])
        raise SystemExit(1)


print("模式=%s  参考=%s  audio_codes=%s" % (MODE, REF, CODES))
r = post("/prompt", {"prompt": WF, "client_id": "acc-test2"})
pid = r.get("prompt_id")
if not pid:
    print("提交失败:", json.dumps(r, ensure_ascii=False)[:2000])
    raise SystemExit(1)
print("已提交 prompt_id =", pid)

t0 = time.time()
for i in range(600):
    time.sleep(3)
    h = get("/history/" + pid)
    if pid in h:
        st = h[pid].get("status", {})
        print("用时 %.0f 秒" % (time.time() - t0))
        print("状态:", st.get("status_str"), "completed =", st.get("completed"))
        if st.get("status_str") == "error":
            for m in st.get("messages", []):
                print("  ", json.dumps(m, ensure_ascii=False)[:1500])
        print("输出:", json.dumps(h[pid].get("outputs", {}), ensure_ascii=False)[:800])
        break
    q = get("/queue")
    print("  等待 %ds  运行 %d  排队 %d" % (int(time.time() - t0),
                                          len(q.get("queue_running", [])),
                                          len(q.get("queue_pending", []))))
else:
    print("超时未完成")
