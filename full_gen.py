"""用指定 seed 出完整长度版本

用法: python full_gen.py 245 2024 full_2024
"""
import json
import sys
import time
import urllib.request

HOST = "http://127.0.0.1:8188"
LYRIC_MD = r"C:/Users/admin/Desktop/kuoleroy/comfyui-workflow/相交线/无情相交线.md"

TAGS = ("industrial dub reggae, heavy sub bass, tape saturation, sparse drum machine, "
        "cavernous spring reverb, male gritty vocal, dark, 72 BPM")

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 245.0
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
PREFIX = sys.argv[3] if len(sys.argv) > 3 else "full_%d" % SEED
TEMP = float(sys.argv[4]) if len(sys.argv) > 4 else 0.85

# 只取到 [Outro] 结束；原文件末尾那段散词（"转身排 担忧的改…"）不是歌词
lines = open(LYRIC_MD, encoding="utf-8").read().splitlines()
keep = []
for ln in lines:
    if ln.strip().startswith("转身排"):
        break
    keep.append(ln)
LYRICS = "\n".join(keep).strip()
print("歌词 %d 行 / %d 字" % (len(keep), len(LYRICS.replace("\n", ""))))

WF = {
    "1": {"class_type": "UNETLoader",
          "inputs": {"unet_name": "acestep_v1.5_turbo.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "DualCLIPLoader",
          "inputs": {"clip_name1": "qwen_0.6b_ace15.safetensors",
                     "clip_name2": "qwen_1.7b_ace15.safetensors", "type": "ace"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ace_1.5_vae.safetensors"}},
    "6": {"class_type": "TextEncodeAceStepAudio1.5",
          "inputs": {"clip": ["2", 0], "tags": TAGS, "lyrics": LYRICS,
                     "seed": SEED, "bpm": 72, "duration": SECONDS,
                     "timesignature": "4", "language": "zh", "keyscale": "A minor",
                     "generate_audio_codes": True, "cfg_scale": 2.0,
                     "temperature": TEMP, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
    "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
    "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
    "9": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
    "10": {"class_type": "KSampler",
           "inputs": {"model": ["9", 0], "seed": SEED, "steps": 8, "cfg": 1.0,
                      "sampler_name": "euler", "scheduler": "simple",
                      "positive": ["6", 0], "negative": ["8", 0],
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


r = post("/prompt", {"prompt": WF, "client_id": "fullgen"})
pid = r.get("prompt_id")
if not pid:
    print("提交失败:", json.dumps(r, ensure_ascii=False)[:2000])
    raise SystemExit(1)
print("已提交 prompt_id =", pid, " 目标时长 %.0f 秒  seed=%d" % (SECONDS, SEED))

t0 = time.time()
for _ in range(1200):
    time.sleep(3)
    h = get("/history/" + pid)
    if pid in h:
        st = h[pid].get("status", {})
        print("用时 %.0f 秒" % (time.time() - t0))
        print("状态:", st.get("status_str"))
        if st.get("status_str") == "error":
            for m in st.get("messages", []):
                print("  ", json.dumps(m, ensure_ascii=False)[:2000])
        print("输出:", json.dumps(h[pid].get("outputs", {}), ensure_ascii=False)[:800])
        break
    if _ % 10 == 0:
        q = get("/queue")
        print("  等待 %ds 运行%d" % (time.time() - t0, len(q.get("queue_running", []))))
else:
    print("超时")
