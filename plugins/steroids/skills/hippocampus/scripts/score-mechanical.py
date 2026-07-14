#!/usr/bin/env python3
"""hippocampus 机械评分器 —— 把评分卡里"能确定计算"的部分算出来，供 agent 直接用。

对应评分卡三段式管线的前两段（跨模型/多次运行完全一致），不做语义判断：
  1. 机械盘点：体量分（指令文件超行扣分 + auto-memory 截断扣分，软链接去重）
  2. 候选生成：断链候选、时效标记候选、含糊线索候选、同主题矛盾候选对

第三段（语义裁决：逐条候选判真伪并记账）由 agent 按 scoring-rubric.md 做。

用法：
  python3 score-mechanical.py \
      --instruction ~/.claude/CLAUDE.md --instruction ./CLAUDE.md \
      --auto-memory ~/.claude/memory/MEMORY.md \
      --repo-root .
所有参数可选：不传时自动探测常见位置。输出 JSON 到 stdout。
仅用 Python 3 标准库。
"""
from __future__ import annotations
import argparse, json, os, re, sys

CAP_LINES = 200          # auto-memory 每次只载前 200 行
CAP_BYTES = 25 * 1024    # 或 25KB，谁先到
LINE_BUDGET = 200        # 单个指令文件的建议行数上限
OVERLINE_CAP = 45        # 超行扣分封顶
TRUNC_WEIGHT = 60        # 截断扣分权重


def est_tokens(text: str) -> int:
    """粗略 token 估算：CJK 约 1 token/字，其余约 1 token/4 字符。仅供参考。"""
    cjk = len(re.findall(r"[㐀-鿿豈-﫿]", text))
    other = len(text) - cjk
    return round(cjk + other / 4)


def file_stats(path: str) -> dict | None:
    p = os.path.expanduser(path)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8", errors="replace") as f:
        text = f.read()
    return {
        "path": path,
        "lines": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        "bytes": len(text.encode("utf-8")),
        "kb": round(len(text.encode("utf-8")) / 1024, 1),
        "est_tokens": est_tokens(text),
        "_text": text,
        "_realpath": os.path.realpath(p),   # 用于软链接去重
    }


def overline_penalty(files: list[dict]) -> float:
    total = sum(max(0, (f["lines"] - LINE_BUDGET) / 20) for f in files)
    return round(min(OVERLINE_CAP, total), 1)


def truncation(auto_mem: dict | None) -> dict:
    """auto-memory 被丢弃比例：载入到 min(200 行, 25KB) 为止，其余算丢弃。"""
    if not auto_mem:
        return {"applicable": False, "dropped_fraction": 0.0, "penalty": 0}
    lines = auto_mem["_text"].splitlines(keepends=True)
    loaded, acc = 0, 0
    for i, ln in enumerate(lines):
        if i >= CAP_LINES:
            break
        b = len(ln.encode("utf-8"))
        if acc + b > CAP_BYTES:
            break
        acc += b
        loaded = acc
    total = auto_mem["bytes"] or 1
    dropped = max(0.0, 1 - loaded / total)
    return {
        "applicable": True,
        "loaded_bytes": loaded,
        "total_bytes": total,
        "dropped_fraction": round(dropped, 3),
        "penalty": round(TRUNC_WEIGHT * dropped),
    }


# 只认"明显是本地文件路径"的引用，保守，尽量不误报
PATH_RE = re.compile(r"`([^`\n]+)`|(?<![\w`])((?:~|\.\.?|\$HOME|\$\{HOME\})/[^\s`)'\"]+)")


def looks_like_path(s: str) -> bool:
    s = s.strip()
    if "/" not in s or " " in s or len(s) > 200:
        return False
    if s.startswith(("http://", "https://", "git@")):
        return False
    if "..." in s or "<" in s or ">" in s:   # 明显占位符，不当引用
        return False
    # 需要像文件（有扩展名）或以 ~ / . / $HOME 开头
    return bool(re.search(r"\.\w{1,6}$", s)) or s.startswith(("~", "./", "../", "$HOME", "${HOME}"))


def broken_links(files: list[dict], repo_root: str) -> list[dict]:
    out, seen = [], set()
    for f in files:
        for i, line in enumerate(f["_text"].splitlines(), 1):
            for m in PATH_RE.finditer(line):
                cand = (m.group(1) or m.group(2) or "").strip()
                if not cand or not looks_like_path(cand):
                    continue
                exp = os.path.expanduser(os.path.expandvars(cand))
                # 相对路径按 repo_root 解析
                probe = exp if os.path.isabs(exp) else os.path.join(repo_root, exp)
                if not os.path.exists(probe):
                    key = (f["path"], cand)
                    if key not in seen:
                        seen.add(key)
                        out.append({"file": f["path"], "line": i, "ref": cand})
    return out


# ---------- 候选生成：只列候选，不判定；语义裁决由 agent 按 scoring-rubric.md 做 ----------
STALE_RE = re.compile(r"临时|WIP|TODO|FIXME|待(?:官方)?修复|过渡方案|暂时方案|占位|deprecated", re.I)
DATE_RE = re.compile(r"20\d{2}\s*[-/年.]\s*\d{1,2}")
VAGUE_RE = re.compile(
    r"注意(?!入|册)|合理|适当|视情况|酌情|尽量|保持[^，。;：]{0,6}(?:整洁|干净|一致|可维护)|良好实践|best\s*practice", re.I)
TOKEN_RE = re.compile(r"`([^`\n]{2,40})`|(?<![\w/.-])([A-Za-z][\w-]{3,30})(?![\w/.-])")
COMMON_TOKENS = {
    "http", "https", "github", "claude", "codex", "agents", "agent", "skill", "skills",
    "json", "yaml", "html", "readme", "install", "true", "false", "null", "with", "from",
    "this", "that", "file", "files", "name", "path", "user", "home", "config", "shell",
}


def _lines(files: list[dict]):
    for f in files:
        for i, raw in enumerate(f["_text"].splitlines(), 1):
            line = raw.strip()
            if line:
                yield f["path"], i, line


def _cue_candidates(files: list[dict], *regexes, cap: int = 40) -> list[dict]:
    out, seen = [], set()
    for path, i, line in _lines(files):
        for rx in regexes:
            m = rx.search(line)
            if m and (path, i) not in seen:
                seen.add((path, i))
                out.append({"file": path, "line": i, "cue": m.group(0)[:24], "text": line[:90]})
                break
        if len(out) >= cap:
            break
    return out


def _contradiction_topics(files: list[dict], cap: int = 25) -> list[dict]:
    """同一主题词出现在多处（跨文件，或同文件相距 ≥40 行）→ 矛盾候选对。
    仅启发式（对中文裸主题覆盖有限），agent 仍需按评分卡做补充性自由扫描。"""
    from collections import defaultdict
    topics = defaultdict(list)
    for path, i, line in _lines(files):
        seen_here = set()
        for m in TOKEN_RE.finditer(line):
            tok = (m.group(1) or m.group(2) or "").strip().lower()
            if not tok or len(tok) < 4 or tok in COMMON_TOKENS or tok in seen_here:
                continue
            seen_here.add(tok)
            topics[tok].append({"file": path, "line": i, "text": line[:90]})
    out = []
    for tok, occ in topics.items():
        if not (2 <= len(occ) <= 8):        # 出现太多 = 太通用，不作主题
            continue
        span_files = {o["file"] for o in occ}
        same_file_far = len(span_files) == 1 and (occ[-1]["line"] - occ[0]["line"] >= 40)
        if len(span_files) >= 2 or same_file_far:
            out.append({"topic": tok, "occurrences": occ[:4]})
    out.sort(key=lambda t: (-len({o['file'] for o in t['occurrences']}), -len(t["occurrences"])))
    return out[:cap]


def autodetect(kind: str) -> list[str]:
    home = os.path.expanduser("~")
    cands = {
        "instruction": [f"{home}/.claude/CLAUDE.md", f"{home}/.claude/AGENTS.md",
                        "CLAUDE.md", "AGENTS.md"],
        "auto_memory": [f"{home}/.claude/memory/MEMORY.md", f"{home}/.claude/MEMORY.md"],
    }[kind]
    return [c for c in cands if os.path.isfile(os.path.expanduser(c))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instruction", action="append", default=[],
                    help="指令文件 CLAUDE.md/AGENTS.md（可多次）")
    ap.add_argument("--auto-memory", default=None, help="Claude auto-memory 文件（可选）")
    ap.add_argument("--repo-root", default=".", help="解析相对路径引用的根")
    a = ap.parse_args()

    inst_paths = a.instruction or autodetect("instruction")
    files, _seen_rp = [], set()
    for s in (file_stats(p) for p in inst_paths):
        if not s:
            continue
        if s["_realpath"] in _seen_rp:   # 软链接/重复路径指向同一文件，只算一次
            continue
        _seen_rp.add(s["_realpath"])
        files.append(s)
    if not files:
        print(json.dumps({"error": "未找到任何指令文件（CLAUDE.md/AGENTS.md）"}, ensure_ascii=False))
        sys.exit(0)

    am_path = a.auto_memory or (autodetect("auto_memory")[:1] or [None])[0]
    auto_mem = file_stats(am_path) if am_path else None

    op = overline_penalty(files)
    tr = truncation(auto_mem)
    bloat = max(0, round(100 - op - tr["penalty"]))
    candidates = {
        "broken_links": broken_links(files, os.path.abspath(os.path.expanduser(a.repo_root))),
        "staleness": _cue_candidates(files, STALE_RE, DATE_RE),
        "vagueness": _cue_candidates(files, VAGUE_RE),
        "contradiction_topics": _contradiction_topics(files),
    }

    for f in files:
        f.pop("_text", None)
        f.pop("_realpath", None)
    if auto_mem:
        auto_mem.pop("_text", None)
        auto_mem.pop("_realpath", None)

    print(json.dumps({
        "bloat": {
            "score": bloat,
            "overline_penalty": op,
            "truncation": tr,
            "instruction_files": files,
            "auto_memory": {k: v for k, v in (auto_mem or {}).items()} or None,
        },
        # 各维度候选：机械生成，agent 逐条裁决（真缺陷记入账本，文档举例/误报丢弃）。
        "candidates": candidates,
        "rubric_version": 2,
        "note": "体量为纯机械项、可复现。candidates 是待裁决清单，不是缺陷判定；矛盾维度另需补充性自由扫描。语义裁决按 scoring-rubric.md。token 估算为粗略值。",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
