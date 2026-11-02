"""批量出 N 个 seed 的纯文本版本，用于比较「同一套标签下音色能拉开多少」

用法: python batch_seed.py 25 8
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
就被齿轮的洪流冲散"""

SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 8


def wf(seed, prefix):
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "acestep_v1.5_turbo.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": "qwen_0.6b_ace15.safetensors",
                         "clip_name2": "qwen_1.7b_ace15.safetensors", "type": "ace"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ace_1.5_vae.safetensors"}},
        "6": {"class_type": "TextEncodeAceStepAudio1.5",
              "inputs": {"clip": ["2", 0], "tags": TAGS, "lyrics": LYRICS,
                         "seed": seed, "bpm": 72, "duration": SECONDS,
                         "timesignature": "4", "language": "zh", "keyscale": "A minor",
                         "generate_audio_codes": True, "cfg_scale": 2.0,
                         "temperature": 0.85, "top_p": 0.9, "top_k": 0, "min_p": 0.0}},
        "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "9": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
        "10": {"class_type": "KSampler",
               "inputs": {"model": ["9", 0], "seed": seed, "steps": 8, "cfg": 1.0,
                          "sampler_name": "euler", "scheduler": "simple",
                          "positive": ["6", 0], "negative": ["8", 0],
                          "latent_image": ["11", 0], "denoise": 1.0}},
        "11": {"class_type": "EmptyAceStep1.5LatentAudio",
               "inputs": {"seconds": SECONDS, "batch_size": 1}},
        "12": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["10", 0], "vae": ["3", 0]}},
        "13": {"class_type": "SaveAudio", "inputs": {"audio": ["12", 0], "filename_prefix": prefix}},
    }


def get(path):
    return json.loads(urllib.request.urlopen(HOST + path, timeout=30).read())


def post(path, obj):
    req = urllib.request.Request(HOST + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode("utf-8", "replace")[:1500])
        raise SystemExit(1)


SEEDS = [42, 137, 2024, 7, 999, 512, 88, 3141][:COUNT]

for i, sd in enumerate(SEEDS, 1):
    prefix = "seedvar_%02d" % i
    r = post("/prompt", {"prompt": wf(sd, prefix), "client_id": "seedvar"})
    pid = r.get("prompt_id")
    if not pid:
        print("提交失败", sd, json.dumps(r, ensure_ascii=False)[:600])
        continue
    t0 = time.time()
    for _ in range(400):
        time.sleep(2)
        h = get("/history/" + pid)
        if pid in h:
            st = h[pid].get("status", {})
            ok = st.get("status_str") == "success"
            print("[%d/%d] seed=%-5d %s  %.0fs" % (i, len(SEEDS), sd,
                                                   "OK" if ok else "FAIL", time.time() - t0))
            break
    else:
        print("[%d/%d] seed=%d 超时" % (i, len(SEEDS), sd))
