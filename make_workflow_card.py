"""在已有工作流上，加一条「音色卡」通路。

LoadAudio → VAEEncodeAudio → ReferenceTimbreAudio → KSampler.positive
同时把 generate_audio_codes 关掉（有参考音频时它会被强制丢弃，开着只是白跑一遍 LM）。
"""
import io
import json
import os

CV = r"C:/Users/admin/AppData/Local/Comfy-Desktop/ComfyUI-Installs/local/ComfyUI"
SRC = os.path.join(CV, "user", "default", "workflows", "ACE_相交线_生成.json")
DST = os.path.join(CV, "user", "default", "workflows", "ACE_相交线_音色卡版.json")

CARD = "timbre_2024_mix.wav"          # 20 秒完整混音，实测最稳的那张

d = json.load(io.open(SRC, encoding="utf-8"))
nodes = {n["id"]: n for n in d["nodes"]}
links = {l[0]: l for l in d["links"]}

nid = d["last_node_id"]
lid = d["last_link_id"]


def new_id():
    global nid
    nid += 1
    return nid


def new_link():
    global lid
    lid += 1
    return lid


load_id, enc_id, ref_id = new_id(), new_id(), new_id()

# --- LoadAudio ---
nodes[load_id] = {
    "id": load_id, "type": "LoadAudio", "pos": [90, 470], "size": [300, 106],
    "flags": {}, "order": 4, "mode": 0, "inputs": [],
    "outputs": [{"name": "AUDIO", "type": "AUDIO", "links": [], "slot_index": 0}],
    "properties": {"Node name for S&R": "LoadAudio"},
    "widgets_values": [CARD],
}

# --- VAEEncodeAudio ---
l_load_enc = new_link()
enc_in_audio = {"name": "audio", "type": "AUDIO", "link": l_load_enc}
enc_in_vae = {"name": "vae", "type": "VAE", "link": None}
nodes[enc_id] = {
    "id": enc_id, "type": "VAEEncodeAudio", "pos": [90, 620], "size": [260, 46],
    "flags": {}, "order": 5, "mode": 0,
    "inputs": [enc_in_audio, enc_in_vae],
    "outputs": [{"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}],
    "properties": {"Node name for S&R": "VAEEncodeAudio"},
    "widgets_values": [],
}

# --- ReferenceTimbreAudio ---
# 复用 KSampler.positive 那条旧线当「歌词 → 参考音色」的入口，避免重复连线
ks_id = [n["id"] for n in d["nodes"] if n["type"] == "KSampler"][0]
l_ref_cond = nodes[ks_id]["inputs"][1]["link"]
l_enc_ref = new_link()
l_ref_pos = new_link()
nodes[ref_id] = {
    "id": ref_id, "type": "ReferenceTimbreAudio", "pos": [390, 480], "size": [300, 74],
    "flags": {}, "order": 6, "mode": 0,
    "inputs": [{"name": "conditioning", "type": "CONDITIONING", "link": l_ref_cond},
               {"name": "latent", "type": "LATENT", "link": l_enc_ref}],
    "outputs": [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [l_ref_pos], "slot_index": 0}],
    "properties": {"Node name for S&R": "ReferenceTimbreAudio"},
    "widgets_values": [],
}

# 连线：VAE → 编码器
vae_id = [n["id"] for n in d["nodes"] if n["type"] == "VAELoader"][0]
l_vae = new_link()
d["links"].append([l_vae, vae_id, 0, enc_id, 1, "VAE"])
enc_in_vae["link"] = l_vae
nodes[vae_id]["outputs"][0]["links"].append(l_vae)

# 连线：LoadAudio → 编码器
d["links"].append([l_load_enc, load_id, 0, enc_id, 0, "AUDIO"])
nodes[load_id]["outputs"][0]["links"] = [l_load_enc]

# 连线：编码器 → 参考音色
d["links"].append([l_enc_ref, enc_id, 0, ref_id, 1, "LATENT"])
nodes[enc_id]["outputs"][0]["links"] = [l_enc_ref]

# 连线：歌词编码 → 参考音色（复用旧线 254，改指向即可，歌词编码一侧不用动）
links[l_ref_cond][3] = ref_id
links[l_ref_cond][4] = 0

# 连线：参考音色 → KSampler.positive（新开一条）
nodes[ks_id]["inputs"][1]["link"] = l_ref_pos
d["links"].append([l_ref_pos, ref_id, 0, ks_id, 1, "CONDITIONING"])

# 关掉 audio codes（有参考音频时它会被丢弃）
te_id = [n["id"] for n in d["nodes"] if n["type"] == "TextEncodeAceStepAudio1.5"][0]
te = nodes[te_id]
wv = te["widgets_values"]
wv[9] = False
te["widgets_values"] = wv

d["last_node_id"] = nid
d["last_link_id"] = lid
d["nodes"] = list(nodes.values())

json.dump(d, io.open(DST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已写入:", DST)
print("新增节点:", load_id, enc_id, ref_id, "| 音色卡 =", CARD)
