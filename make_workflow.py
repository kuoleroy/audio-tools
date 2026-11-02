"""把官方 ACE-Step 1.5 蓝图展平成普通工作流，参数改成本机可跑通的配置。

输出到 ComfyUI 的 user/default/workflows/，界面上侧边栏直接能打开。
"""
import copy
import io
import json
import os

CV = r"C:/Users/admin/AppData/Local/Comfy-Desktop/ComfyUI-Installs/local/ComfyUI"
SRC = os.path.join(CV, "blueprints", "Text to Audio (ACE-Step 1.5).json")
DST = os.path.join(CV, "user", "default", "workflows", "ACE_相交线_生成.json")
LYRIC_MD = r"C:/Users/admin/Desktop/kuoleroy/comfyui-workflow/相交线/无情相交线.md"

# ---------- 参数 ----------
TAGS = ("industrial dub reggae, heavy sub bass, tape saturation, sparse drum machine, "
        "cavernous spring reverb, male gritty vocal, dark, 72 BPM")
SECONDS = 205
SEED = 2024
TEMPERATURE = 0.70

# 歌词只取到 [Outro] 结束
lines = io.open(LYRIC_MD, encoding="utf-8").read().splitlines()
keep = []
for ln in lines:
    if ln.strip().startswith("转身排"):
        break
    keep.append(ln)
LYRICS = "\n".join(keep).strip()

LAYOUT = {
    104: (-700, 160, 340, 82),
    105: (-700, 290, 340, 130),
    106: (-700, 470, 340, 58),
    78:  (-300, 160, 290, 58),
    94:  (-300, 260, 330, 460),
    47:  (90, 260, 240, 46),
    98:  (90, 350, 240, 82),
    3:   (390, 160, 300, 262),
    18:  (740, 160, 240, 46),
}

data = json.load(io.open(SRC, encoding="utf-8"))
sg = data["definitions"]["subgraphs"][0]
nodes = copy.deepcopy(sg["nodes"])

# 去掉两个辅助节点：PrimitiveNode(102) / PrimitiveFloat(110)
nodes = [n for n in nodes if n["id"] not in (102, 110)]
ids = {n["id"] for n in nodes}

# 只保留两端都还在的连线；指向子图输入(-10) / 输出的线全部断开
links = [l for l in sg["links"]
         if l["origin_id"] in ids and l["target_id"] in ids]
kept = {l["id"] for l in links}

for n in nodes:
    for i in n.get("inputs") or []:
        if i.get("link") not in kept:
            i["link"] = None
    for o in n.get("outputs") or []:
        if o.get("links"):
            o["links"] = [x for x in o["links"] if x in kept]

byname = {n["type"]: n for n in nodes}

# ---------- 填参数 ----------
# DualCLIPLoader：第二个槽换成 1.7B（本机没有 4B，sd.py 会按 qwen3_2b 建结构）
byname["DualCLIPLoader"]["widgets_values"] = [
    "qwen_0.6b_ace15.safetensors", "qwen_1.7b_ace15.safetensors", "ace", "default"]

# VAELoader / UNETLoader 文件名确认
byname["VAELoader"]["widgets_values"] = ["ace_1.5_vae.safetensors"]
byname["UNETLoader"]["widgets_values"] = ["acestep_v1.5_turbo.safetensors", "default"]

# 歌词编码：tags, lyrics, seed, control, bpm, duration, 拍号, 语言, 调, codes, cfg, temp, top_p, top_k, min_p
byname["TextEncodeAceStepAudio1.5"]["widgets_values"] = [
    TAGS, LYRICS, SEED, "fixed", 72, float(SECONDS), "4", "zh", "A minor",
    True, 2.0, TEMPERATURE, 0.9, 0, 0.0]

# 空 latent：秒数
byname["EmptyAceStep1.5LatentAudio"]["widgets_values"] = [float(SECONDS), 1]

# KSampler：seed, control, steps, cfg, sampler, scheduler, denoise
byname["KSampler"]["widgets_values"] = [SEED, "fixed", 8, 1.0, "euler", "simple", 1.0]

# ---------- 补一个 SaveAudio ----------
max_id = max(ids)
save_id = max_id + 1
max_link = max(kept)
save_link = max_link + 1

nodes.append({
    "id": save_id, "type": "SaveAudio", "pos": [740, 260], "size": [300, 96],
    "flags": {}, "order": 9, "mode": 0,
    "inputs": [{"name": "audio", "type": "AUDIO", "link": save_link}],
    "outputs": [],
    "properties": {"Node name for S&R": "SaveAudio"},
    "widgets_values": ["ace_step15/相交线"],
})
links.append({"id": save_link, "origin_id": 18, "origin_slot": 0,
              "target_id": save_id, "target_slot": 0, "type": "AUDIO"})
byname["VAEDecodeAudio"]["outputs"][0]["links"] = [save_link]

# ---------- 排位置 ----------
for n in nodes:
    box = LAYOUT.get(n["id"])
    if box:
        n["pos"] = [box[0], box[1]]
        n["size"] = [box[2], box[3]]

for order, n in enumerate(sorted(nodes, key=lambda x: (x["pos"][0], x["pos"][1]))):
    n["order"] = order
    n.pop("widget", None)

# 顶层 links 用数组格式，兼容性最好
flat_links = [[l["id"], l["origin_id"], l["origin_slot"],
               l["target_id"], l["target_slot"], l["type"]] for l in links]

out = {
    "last_node_id": save_id,
    "last_link_id": save_link,
    "nodes": nodes,
    "links": flat_links,
    "groups": [],
    "config": {},
    "extra": {},
    "version": 0.4,
}

os.makedirs(os.path.dirname(DST), exist_ok=True)
json.dump(out, io.open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已写入:", DST)
print("节点 %d 个 / 连线 %d 条 / 歌词 %d 字 / 时长 %ds / seed %d / temp %.2f"
      % (len(nodes), len(flat_links), len(LYRIC_SKIP := LYRICS.replace("\n", "")),
         SECONDS, SEED, TEMPERATURE))
