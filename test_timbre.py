"""音色卡验证：同一段陌生歌词 + 不同音色卡，看输出人声是否跟着卡走

用法: python test_timbre.py 25 timbre_2024_main wfcardA
"""
import json
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:8188"

TAGS = ("industrial dub reggae, heavy sub bass, tape saturation, sparse drum machine, "
        "cavernous spring reverb, male gritty vocal, dark, 72 BPM")

# 故意用另一首歌的词，避免模型"复现"原曲
LYRICS = """[Verse]
把痛调成静音
让它一直响
调到最大声
还是听不见

[Chorus]
把痛调成静音
调到最大声"""

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
CARD = sys.argv[2] if len(sys.argv) > 2 else "timbre_2024_main.wav"
PREFIX = sys.argv[3] if len(sys.argv) > 3 else "wfcardA"

WF = {
    "1": {"class_type": "UNETLoader",
          "inputs": {"unet_name": "acestep_v1.5_turbo.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "DualCLIPLoader",
          "inputs": {"clip_name1": "qwen_0.6b_ace15.safetensors",
                     "clip_name2": "qwen_1.7b_ace15.safetensors", "type": "ace"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ace_1.5_vae.safetensors"}},
    "4": {"class_type": "LoadAudio", "inputs": {"audio": CARD}},
    "5": {"class_type": "VAEEncodeAudio", "inputs": {"audio": ["4", 0], "vae": ["3", 0]}},
    "6": {"class_type": "TextEncodeAceStepAudio1.5",
          "inputs": {"clip": ["2", 0], "tags": TAGS, "lyrics": LYRICS,
                     "seed": 777, "bpm": 72, "duration": SECONDS,
                     "timesignature": "4", "language": "zh", "keyscale": "A minor",
                     "generate_audio_codes": False, "cfg_scale": 2.0,
                     "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
    "7": {"class_type": "ReferenceTimbreAudio",
          "inputs": {"conditioning": ["6", 0], "latent": ["5", 0]}},
    "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
    "9": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
    "10": {"class_type": "KSampler",
           "inputs": {"model": ["9", 0], "seed": 777, "steps": 8, "cfg": 1.0,
                      "sampler_name": "euler", "scheduler": "simple",
                      "positive": ["7", 0], "negative": ["8", 0],
                      "latent_image": ["11", 0], "denoise": 1.0}},
    "11": {"class_type": "EmptyAceStep1.5LatentAudio",
           "inputs": {"seconds": SECONDS, "batch_size": 1}},
    "12": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
    "13": {"class_type": "SaveAudio", "inputs": {"audio": ["12", 0], "filename_prefix": PREFIX}},
}


def get(path):
    return json.loads(urllib.request.urlopen(HOST + path, timeout=30).read())


def post(path, obj):
    req = urllib.request.Request(HOST + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode("utf-8", "replace")[:3000])
        raise SystemExit(1)


r = post("/prompt", {"prompt": WF, "client_id": "timbrecard"})
pid = r.get("prompt_id")
if not pid:
    print("提交失败:", json.dumps(r, ensure_ascii=False)[:2000])
    raise SystemExit(1)
print("已提交", pid, "| 卡 =", CARD, "| 时长 %.0fs" % SECONDS)

t0 = time.time()
for i in range(400):
    time.sleep(3)
    h = get("/history/" + pid)
    if pid in h:
        st = h[pid].get("status", {})
        print("用时 %.0f 秒 | 状态 %s" % (time.time() - t0, st.get("status_str")))
        if st.get("status_str") == "error":
            for m in st.get("messages", []):
                print("  ", json.dumps(m, ensure_ascii=False)[:1500])
        print("输出:", json.dumps(h[pid].get("outputs", {}), ensure_ascii=False)[:400])
        break
else:
    print("超时")
