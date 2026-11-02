# -*- coding: utf-8 -*-
"""用 ComfyUI 的 API 出《讽庄谣》MV 背景图（Qwen-Image 2.1）。

不用手点界面：直接 POST /prompt 排队，轮询 /history 取回图片。
用法: python comfy_t2i.py <prompt> <negative> <seed> <前缀> [宽 高 步数]
"""
import sys, os, json, time, urllib.request, uuid

HOST = "http://127.0.0.1:8188"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "lrc", "fz", "out", "last_t2i.json")

pos = sys.argv[1]
neg = sys.argv[2] if len(sys.argv) > 2 else "text, letters, watermark, logo, signature, person, face, hands, colorful, glossy, smooth gradient, cartoon, blurry, lowres, jpeg artifacts, cluttered, frame, border"
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
prefix = sys.argv[4] if len(sys.argv) > 4 else "fz_bg"
W = int(sys.argv[5]) if len(sys.argv) > 5 else 1024
H = int(sys.argv[6]) if len(sys.argv) > 6 else 1536
STEPS = int(sys.argv[7]) if len(sys.argv) > 7 else 16

MODEL = "qwen_image_2.1_turbo_int8_convrot.safetensors"

prompt = {
    "62": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "qwen3vl_8b_w4a8.safetensors", "type": "qwen_image", "device": "default"}},
    "63": {"class_type": "VAELoader", "inputs": {
        "vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
    "66": {"class_type": "UNETLoader", "inputs": {
        "unet_name": MODEL, "weight_dtype": "default"}},
    "67": {"class_type": "CLIPTextEncode", "inputs": {"text": pos, "clip": ["62", 0]}},
    "68": {"class_type": "EmptySD3LatentImage", "inputs": {
        "width": W, "height": H, "batch_size": 1}},
    "69": {"class_type": "ModelSamplingAuraFlow", "inputs": {
        "model": ["66", 0], "shift": 3, "sampling": "flow"}},
    "70": {"class_type": "KSampler", "inputs": {
        "model": ["69", 0], "positive": ["67", 0], "negative": ["71", 0],
        "latent_image": ["68", 0], "seed": seed, "steps": STEPS, "cfg": 1.0,
        "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0}},
    "71": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["62", 0]}},
    "65": {"class_type": "VAEDecode", "inputs": {"samples": ["70", 0], "vae": ["63", 0]}},
    "9": {"class_type": "SaveImage", "inputs": {"images": ["65", 0], "filename_prefix": prefix}},
}

cid = str(uuid.uuid4())
body = json.dumps({"prompt": prompt, "client_id": cid}).encode()
req = urllib.request.Request(f"{HOST}/prompt", data=body,
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as r:
    res = json.loads(r.read())
pid = res["prompt_id"]
print("[queue] prompt_id =", pid, flush=True)

t0 = time.time()
while True:
    time.sleep(3)
    with urllib.request.urlopen(f"{HOST}/history/{pid}", timeout=30) as r:
        h = json.loads(r.read())
    if pid in h:
        out = h[pid].get("outputs", {})
        imgs = []
        for node_out in out.values():
            imgs += node_out.get("images", [])
        if imgs:
            print(f"[done] {time.time()-t0:.0f}s")
            for im in imgs:
                print(f"  filename={im.get('filename')}  subfolder={im.get('subfolder','')}")
            os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
            json.dump(imgs, open(OUT_JSON, "w"),
                      ensure_ascii=False, indent=1)
            break
    if time.time() - t0 > 900:
        print("[timeout]")
        sys.exit(1)
