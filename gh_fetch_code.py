# -*- coding: utf-8 -*-
"""用 GitHub API 并行拉取仓库里的代码文件（跳过权重/ffmpeg/测试/设计稿）。

比 git clone 快得多：这机器到 GitHub 只有 40-60 KB/s，但 API 走的是另一条通道。
用法: python gh_fetch_code.py <repo> <dest> [--with-design]
"""
import sys, os, json, base64, urllib.request, urllib.error, subprocess
from concurrent.futures import ThreadPoolExecutor

repo = sys.argv[1]
dest = sys.argv[2]
with_design = "--with-design" in sys.argv

SKIP = ("backend/models/", "backend/ffmpeg/", "test/", "design/")

try:
    tok = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
except Exception:
    tok = ""

API = f"https://api.github.com/repos/{repo}"
HEAD = {"Accept": "application/vnd.github+json"}
if tok:
    HEAD["Authorization"] = f"Bearer {tok}"


def get_json(url):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


tree = get_json(f"{API}/git/trees/main?recursive=1")
files = [t["path"] for t in tree.get("tree", [])
         if t["type"] == "blob" and not any(t["path"].startswith(s) for s in SKIP)]
if with_design:
    files += [t["path"] for t in tree.get("tree", [])
              if t["type"] == "blob" and t["path"].startswith("design/")]
print(f"[tree] 要拉 {len(files)} 个文件")


def fetch(path):
    out = os.path.join(dest, path.replace("/", os.sep))
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return (path, "skip")
    try:
        d = get_json(f"{API}/contents/{urllib.parse.quote(path)}")
        data = base64.b64decode(d["content"])
    except urllib.error.HTTPError as e:
        return (path, f"HTTP {e.code}")
    except Exception as e:
        return (path, f"ERR {e}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
    return (path, len(data))


import urllib.parse
ok = err = 0
with ThreadPoolExecutor(max_workers=8) as ex:
    for path, st in ex.map(fetch, files):
        if st == "skip":
            continue
        if isinstance(st, int):
            ok += 1
        else:
            err += 1
            print(f"  ✗ {path}  {st}")
print(f"[done] 成功 {ok}，失败 {err} → {dest}")
