#!/usr/bin/env python3
# fetch_notes.py  – fully-automatic GetNotes → Markdown pipeline
#
# 1.  prerequisites (run once):
#       pip install requests html2text
# 2.  set two env-vars (refresh after each re-login):
#       export BIJI_BEARER='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.…'
#       export BIJI_CSRF='t6jyASoSB0vyLEF0Z-s4IMUM'
# 3.  test:   python3 fetch_notes.py
# 4.  cron:   0 7 * * * /usr/bin/python3 /path/to/fetch_notes.py

import os, time, json, zipfile, io, hashlib, pathlib, datetime, requests, html2text, sys

# ── config ──────────────────────────────────────────────────────────────────────
HOST        = "https://get-notes.luojilab.com"
BEARER      = os.getenv("BIJI_BEARER")
CSRF        = os.getenv("BIJI_CSRF")
if not (BEARER and CSRF):
    sys.exit("🔴  export BIJI_BEARER and BIJI_CSRF first")

HEAD = {
    "Authorization": f"Bearer {BEARER}",
    "Xi-Csrf-Token": CSRF,
    "Origin": "https://www.biji.com",
    "Referer": "https://www.biji.com/",
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json;charset=UTF-8",
}
OUT_ROOT    = pathlib.Path("daily_notes")
STATE_JSON  = pathlib.Path("state.json")
OUT_ROOT.mkdir(exist_ok=True)

# ── persistent dedup list ───────────────────────────────────────────────────────
seen = set()
if STATE_JSON.exists():
    try:
        seen.update(json.loads(STATE_JSON.read_text())["seen"])
    except Exception:
        pass

# ── 1 · create export task ──────────────────────────────────────────────────────
create_url = f"{HOST}/voicenotes/web/sync/export/create"
resp = requests.post(create_url, headers=HEAD, json={"type": "zip "})
try:
    task_id = resp.json()["c"]["data"]["id"]
except Exception:
    sys.exit(f"🔴 create failed ({resp.status_code}): {resp.text[:200]}")

# ── 2 · poll until status = success ─────────────────────────────────────────────
poll_url = f"{HOST}/voicenotes/web/sync/export/tasks/{task_id}"
while True:
    info = requests.get(poll_url, headers=HEAD).json()["c"]
    if info["status"] == "success":
        access_url = info["access_url"]
        break
    if info["status"] == "failed":
        sys.exit("🔴 server marked task failed")
    time.sleep(3)

# ── 3 · download zip via CDN link (no headers needed) ───────────────────────────
zip_bytes = requests.get(access_url, timeout=120).content

# ── 4 · unzip, convert HTML→MD, incremental save ───────────────────────────────
today_dir = OUT_ROOT / datetime.date.today().isoformat()
today_dir.mkdir(parents=True, exist_ok=True)
new_cnt = 0
conv = html2text.HTML2Text()
conv.body_width = 0

with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
    for name in zf.namelist():
        if not name.endswith(".html"):
            continue
        raw = zf.read(name)
        md5 = hashlib.md5(raw).hexdigest()
        if md5 in seen:
            continue                  # skip duplicates
        markdown = conv.handle(raw.decode("utf-8"))
        (today_dir / f"{name[:-5]}.md").write_text(markdown, encoding="utf-8")
        seen.add(md5)
        new_cnt += 1

STATE_JSON.write_text(json.dumps({"seen": list(seen)}))
print(f"✅ {new_cnt} new notes saved to {today_dir}")
