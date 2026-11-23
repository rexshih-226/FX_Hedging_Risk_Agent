"""Read-only official-source downloader; snapshots remain unverified evidence."""
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

from .contracts import ROOT, read_json, write_json


def fetch_source(source_id, user_agent, output_dir, store):
    catalog = read_json(ROOT / "config" / "sources.json")
    source = next((s for s in catalog["sources"] if s["source_id"] == source_id), None)
    if source is None:
        raise ValueError("Unknown source_id")
    if not source.get("download_url"):
        raise ValueError("此來源目前只有查詢／文件入口，尚未實作下載介接；請參閱 docs/resources.md")
    if not user_agent.strip():
        raise ValueError("請提供包含專案名稱與聯絡方式的 User-Agent")
    req = Request(source["download_url"], headers={"User-Agent": user_agent, "Accept": "application/json,text/plain,*/*"})
    # One request, no parallel crawling or automatic retry. Error leaves no approved rule.
    with urlopen(req, timeout=20) as response:
        raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError("Snapshot exceeds 10 MB demo limit")
        content_type = response.headers.get("Content-Type", "")
        if source["source_id"] == "sec_submissions":
            import json
            payload = json.loads(raw)
            if str(payload.get("cik")).lstrip("0") != "1045810" or "filings" not in payload:
                raise ValueError("SEC response is not the expected NVIDIA submissions JSON")
        final_url = response.url
    checksum = sha256(raw).hexdigest()
    snapshot_id = source_id + "-" + checksum
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{snapshot_id}.raw"
    target.write_bytes(raw)
    metadata = {
        "snapshot_id": snapshot_id, "source_id": source_id,
        "requested_url": source["download_url"], "final_url": final_url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "sha256": checksum,
        "content_type": content_type, "path": str(target.resolve()),
        "status": "UNVERIFIED", "may_activate_rule": False,
    }
    write_json(directory / f"{snapshot_id}.metadata.json", metadata)
    store.save_source(metadata)
    return metadata
