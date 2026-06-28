#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch YouTube captions + chapters and emit a translation skeleton (work.json).

Usage:
    python3 fetch_transcript.py "<youtube-url>" [out.json]

Output: work.json with meta + chapters + segments. Each segment has the English
(original) text filled and an empty `zh` field for the agent to translate.
yt-dlp is invoked via `uvx yt-dlp` so no global install is needed. Browser cookies
are used to bypass YouTube's bot check; cookie extraction is occasionally flaky, so
the fetch retries a few times.
"""
import json, re, subprocess, sys, tempfile, os, html

UA_RETRIES = 6

def run_ytdlp(args, capture=True):
    cmd = ["uvx", "yt-dlp", "--cookies-from-browser", "chrome", *args]
    return subprocess.run(cmd, capture_output=capture, text=True)

def fetch_info(url):
    """Download info.json (title/duration/chapters/automatic_captions). Retries."""
    for i in range(UA_RETRIES):
        with tempfile.TemporaryDirectory() as d:
            r = run_ytdlp(["--skip-download", "--write-info-json",
                           "--ignore-no-formats-error", "-o", f"{d}/%(id)s.%(ext)s", url])
            f = next((os.path.join(d, x) for x in os.listdir(d) if x.endswith(".info.json")), None)
            if f:
                return json.load(open(f, encoding="utf-8"))
        if "bot" in (r.stderr or "").lower():
            continue
    raise SystemExit("Failed to fetch info.json (bot check / cookies). Make sure you are logged into YouTube in Chrome and retry.")

def pick_sublang(info):
    auto = info.get("automatic_captions") or {}
    lang = info.get("language") or "en"
    for cand in (f"{lang}-orig", lang, "en-orig", "en"):
        if cand in auto:
            return cand
    orig = [k for k in auto if k.endswith("-orig")]
    if orig:
        return orig[0]
    return next(iter(auto), "en")

def fetch_captions(url, vid, sublang):
    for i in range(UA_RETRIES):
        with tempfile.TemporaryDirectory() as d:
            run_ytdlp(["--skip-download", "--write-auto-subs", "--sub-langs", sublang,
                       "--sub-format", "json3", "--ignore-no-formats-error",
                       "-o", f"{d}/%(id)s.%(ext)s", url])
            f = next((os.path.join(d, x) for x in os.listdir(d) if x.endswith(".json3")), None)
            if f:
                return json.load(open(f, encoding="utf-8"))
    raise SystemExit("Failed to download captions. The video may have no captions, or cookies failed.")

def json3_to_lines(cap):
    """Word-level json3 -> list of (startMs, text) lines."""
    lines, words, start = [], [], None
    for e in cap.get("events", []):
        segs = e.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs)
        if not text.strip():
            if words:
                lines.append((start, "".join(words).strip()))
                words, start = [], None
            continue
        if start is None:
            start = e["tStartMs"]
        words.append(text)
    if words:
        lines.append((start, "".join(words).strip()))
    return [(t, x) for t, x in lines if x]

def merge_segments(lines, target=320, hard=620):
    """Merge word-lines into readable segments, breaking on sentence boundaries."""
    out, buf, start = [], [], None
    def flush():
        if buf:
            out.append((start, " ".join(buf).strip()))
    for t, x in lines:
        if start is None:
            start = t
        buf.append(x)
        joined = " ".join(buf)
        ends = joined.rstrip().endswith((".", "?", "!", "”", "…"))
        if (len(joined) >= target and ends) or len(joined) >= hard:
            flush(); buf, start = [], None
    flush()
    return out

def s2ts(ms):
    s = int(ms // 1000)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

def build_chapters(info, segments):
    chs = info.get("chapters") or []
    if not chs:  # synthesize ~5-min windows
        win = 300
        chs = []
        if segments:
            last = segments[-1][0] // 1000
            for st in range(0, int(last) + 1, win):
                chs.append({"start_time": st, "title": f"{st//3600:02d}:{(st%3600)//60:02d} 起"})
    bounds = [(int(c["start_time"]), c["title"]) for c in chs]
    bounds.sort()
    result = [{"title": t, "title_zh": "", "start": s2ts(st * 1000),
               "summary": [], "segments": []} for st, t in bounds]
    def chap_idx(sec):
        idx = 0
        for j, (st, _) in enumerate(bounds):
            if sec >= st:
                idx = j
        return idx
    for ms, text in segments:
        sec = ms / 1000
        result[chap_idx(sec)]["segments"].append(
            {"ts": s2ts(ms), "sec": int(sec), "speaker": "", "en": text, "zh": "", "key": False})
    return [c for c in result if c["segments"]]

def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "work.json"
    info = fetch_info(url)
    vid = info.get("id", "")
    sublang = pick_sublang(info)
    print(f"[fetch] {info.get('title')} | {info.get('duration_string')} | captions={sublang}", file=sys.stderr)
    cap = fetch_captions(url, vid, sublang)
    lines = json3_to_lines(cap)
    segs = merge_segments(lines)
    chapters = build_chapters(info, segs)
    work = {
        "meta": {
            "title": info.get("title", ""), "title_zh": "", "subtitle": "",
            "channel": info.get("channel") or info.get("uploader", ""),
            "guest": "", "duration": info.get("duration_string", ""),
            "upload_date": info.get("upload_date", ""), "video_id": vid,
            "url": f"https://youtu.be/{vid}", "has_speakers": False,
        },
        "chapters": chapters,
        "glossary": [],
    }
    json.dump(work, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(len(c["segments"]) for c in chapters)
    print(f"[fetch] wrote {out}: {len(chapters)} chapters, {n} segments to translate", file=sys.stderr)

if __name__ == "__main__":
    main()
