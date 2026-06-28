#!/usr/bin/env python3
"""
Translate an English epub to bilingual (EN-ZH) format.

Features:
  - Context-aware translation (preceding paragraphs sent as context)
  - Style inheritance (translation mirrors original element's tag and CSS class)
  - Leaf-node deduplication (avoids translating both <li> and its nested <p>)
  - Table cell handling (appends inline instead of creating sibling)
  - lang="zh" marking on all translated elements for downstream filtering

Usage:
  python3 translate_epub.py input.epub -o output.epub
  python3 translate_epub.py input.epub -o output.epub --max-files 5
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from typing import Optional
from pathlib import Path

from lxml import etree

XHTML_NS = "http://www.w3.org/1999/xhtml"
TRANSLATABLE_TAGS = {f"{{{XHTML_NS}}}{t}" for t in ("p", "li", "td", "h1", "h2", "h3", "h4", "h5", "h6")}

MIN_TEXT_LEN = 4
MIN_ALPHA_CHARS = 3
CONTEXT_BEFORE = 5
BATCH_SIZE = 24
CODER_TIMEOUT = 900
DEFAULT_CLAUDE_MODEL = "sonnet"
DEFAULT_CODEX_MODEL = None
DEFAULT_CODEX_EFFORT = "low"
AUTO_RETRY_ROUNDS = 2
AUTO_RETRY_CONTEXT = 8
FORBIDDEN_TRANSLATION_PREFIXES = (
    "我会先",
    "我会",
    "以下是",
    "以下是第",
    "这是我的",
    "1.",
    "1)",
    "first",
    "i will",
    "i can't",
    "cannot",
    "unable",
    "can't",
    "image",
)

ZH_STYLE = """
[lang="zh"] {
    color: #333;
    font-family: "Noto Serif SC", "Source Han Serif SC", "STSongti-SC", "Songti SC", serif;
    font-size: 0.93em;
    line-height: 1.8;
    margin-bottom: 1.3em;
}
"""


def get_text(elem):
    return "".join(elem.itertext()).strip()


def is_ancestor_of_any(elem, candidates):
    for c in candidates:
        parent = c.getparent()
        while parent is not None:
            if parent is elem:
                return True
            parent = parent.getparent()
    return False


def is_attribution_or_name(text):
    """Skip lines that are just attributions or names (e.g. '—Eric Raymond')."""
    stripped = text.lstrip("\u2014\u2013\u2012\u2015-— ")  # strip dashes and spaces
    # Attribution: starts with dash + short remainder that looks like a name
    if text != stripped and len(stripped) < 80:
        return True
    # Very short text that is just a name/title (no verb-like structure)
    if len(text) < 40 and not any(c in text for c in ".,:;!?"):
        words = text.split()
        if len(words) <= 5 and all(w[0].isupper() or not w[0].isalpha() for w in words if w):
            return True
    return False


def collect_translatable_elements(root):
    all_candidates = []
    for elem in root.iter():
        if elem.tag in TRANSLATABLE_TAGS:
            if elem.get("lang") == "zh":
                continue
            text = get_text(elem)
            if not text or len(text) < MIN_TEXT_LEN:
                continue
            alpha = sum(1 for c in text if c.isalpha())
            if alpha < MIN_ALPHA_CHARS:
                continue
            if is_attribution_or_name(text):
                continue
            all_candidates.append(elem)

    return [e for e in all_candidates if not is_ancestor_of_any(e, all_candidates)]


def get_reading_order(extracted_dir):
    """Parse content.opf to get xhtml files in spine reading order."""
    opf_candidates = list(extracted_dir.rglob("*.opf"))
    if not opf_candidates:
        # Fallback: return all xhtml files sorted
        return sorted(extracted_dir.rglob("*.xhtml"))

    opf_path = opf_candidates[0]
    tree = etree.parse(str(opf_path))
    root = tree.getroot()
    ns = {"opf": "http://www.idpf.org/2007/opf"}

    # Build id -> href mapping from manifest
    id_to_href = {}
    for item in root.findall(".//opf:manifest/opf:item", ns):
        item_id = item.get("id")
        href = item.get("href")
        if item_id and href and href.endswith(".xhtml"):
            id_to_href[item_id] = href

    # Get spine order
    ordered = []
    for itemref in root.findall(".//opf:spine/opf:itemref", ns):
        idref = itemref.get("idref")
        if idref in id_to_href:
            full = (opf_path.parent / id_to_href[idref]).resolve()
            if full.exists():
                ordered.append(full)

    return ordered if ordered else sorted(extracted_dir.rglob("*.xhtml"))


def build_prompt(context_texts, batch_texts):
    parts = []
    if context_texts:
        parts.append("=== 以下是前文（仅供理解上下文，不需要翻译）===")
        parts.extend(context_texts)
        parts.append("")

    parts.append("=== 以下是需要翻译的段落 ===")
    for i, t in enumerate(batch_texts):
        parts.append(f"[{i}] {t}")

    text_block = "\n\n".join(parts)

    return f"""你是一位英文学术翻译专家。请将标记了编号的段落翻译为中文。\n\n\
要求：\n1. 只翻译带 [N] 编号的段落，不输出原文\n2. 每段严格使用 "[N]" 开头输出译文，和编号一一对应\n3. 译文自然流畅，避免生硬的中式表达\n\n\
以下是你**不能**输出的内容示例（不要输出）：\n- 我会先翻译第...段\n- 这是我的翻译指令\n- 1. 首先 ...\n\n{text_block}"""


def call_claude_translate(context_texts, batch_texts, model: Optional[str] = None):
    model = model or DEFAULT_CLAUDE_MODEL
    prompt = build_prompt(context_texts, batch_texts)

    try:
        result = subprocess.run(
            ["claude", "-p", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"  [ERROR] Claude CLI failed: {result.stderr[:200]}", file=sys.stderr, flush=True)
            return None
        return parse_translations(result.stdout, len(batch_texts))
    except subprocess.TimeoutExpired:
            print("  [ERROR] Claude CLI timed out", file=sys.stderr, flush=True)
            return None


def call_codex_translate(context_texts, batch_texts, model: Optional[str] = None, effort: Optional[str] = None):
    prompt = build_prompt(context_texts, batch_texts)
    model = model or DEFAULT_CODEX_MODEL
    if model and str(model).strip().lower() == "latest":
        model = DEFAULT_CODEX_MODEL
    effort = effort or DEFAULT_CODEX_EFFORT

    def run_with_options(out_file, extra_args):
        cmd = ["codex", "exec", "--skip-git-repo-check", "--output-last-message", str(out_file)] + extra_args
        if model:
            cmd = cmd + ["-m", model]
        return subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=CODER_TIMEOUT)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "codex_last_message.txt"
        attempt_cmds = []
        if effort:
            attempt_cmds.append(["-c", f'model.reasoning_effort="{effort}"'])
        attempt_cmds.append([])

        try:
            result = None
            for idx, extra_args in enumerate(attempt_cmds):
                if idx > 0:
                    print("  [WARN] Codex first attempt with effort override failed, retrying without override", file=sys.stderr, flush=True)
                result = run_with_options(out_file, extra_args)

                if result.returncode == 0 and out_file.exists():
                    return parse_translations(out_file.read_text(encoding="utf-8"), len(batch_texts))

                err_hint = (result.stderr or result.stdout or "").strip().lower()
                if model and (
                    "invalid model" in err_hint or "unknown" in err_hint or "unsupported" in err_hint
                ):
                    print("  [WARN] Invalid custom model, retrying with default GPT model", file=sys.stderr, flush=True)
                    model = DEFAULT_CODEX_MODEL
                    result = run_with_options(out_file, [])
                    if result.returncode == 0 and out_file.exists():
                        return parse_translations(out_file.read_text(encoding="utf-8"), len(batch_texts))

            preview = (result.stderr or result.stdout or "").strip().replace("\n", " ")[:300]
            print(f"  [ERROR] Codex CLI failed: {preview}", file=sys.stderr, flush=True)
            return None
        except subprocess.TimeoutExpired:
            print("  [ERROR] Codex CLI timed out", file=sys.stderr, flush=True)
            return None


def call_custom_translate(context_texts, batch_texts, cmd: str):
    prompt = build_prompt(context_texts, batch_texts)

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            shell=True,
            capture_output=True,
            text=True,
            timeout=CODER_TIMEOUT,
        )
        if result.returncode != 0:
            preview = (result.stderr or result.stdout or "").strip().replace("\n", " ")[:300]
            print(f"  [ERROR] Custom translator failed: {preview}", file=sys.stderr, flush=True)
            return None
        return parse_translations(result.stdout, len(batch_texts))
    except subprocess.TimeoutExpired:
        print("  [ERROR] Custom translator timed out", file=sys.stderr, flush=True)
        return None


def parse_translations(output, expected_count):
    translations = {}
    pattern = re.compile(r'\[(\d+)\]\s*(.*?)(?=\n\s*\[|\Z)', re.DOTALL)
    for m in pattern.finditer(output):
        idx = int(m.group(1))
        text = m.group(2).strip()
        if text:
            translations[idx] = text

    result = [translations.get(i, "") for i in range(expected_count)]
    found = sum(1 for t in result if t)
    if found < expected_count:
        print(f"  [WARN] Only parsed {found}/{expected_count} translations", flush=True)
    return result


def is_invalid_translation(text):
    if not text or not text.strip():
        return True
    normalized = text.strip().lower()
    return any(normalized.startswith(prefix) for prefix in FORBIDDEN_TRANSLATION_PREFIXES)


def translate_single_paragraph(context_texts, single_text, translator, translator_cmd=None, translator_model=None):
    if translator == "claude":
        return call_claude_translate(context_texts, [single_text], model=translator_model)
    if translator == "codex":
        return call_codex_translate(context_texts, [single_text], model=translator_model)
    return call_custom_translate(context_texts, [single_text], translator_cmd)


def find_missing_indexes(translations):
    missing = []
    for idx, text in enumerate(translations):
        if is_invalid_translation(text):
            missing.append(idx)
    return missing


def add_zh_style(tree):
    head = tree.find(f".//{{{XHTML_NS}}}head")
    if head is None:
        return
    style = etree.SubElement(head, f"{{{XHTML_NS}}}style")
    style.set("type", "text/css")
    style.text = ZH_STYLE


def create_zh_element(original_elem, zh_text):
    zh_elem = etree.Element(original_elem.tag)
    orig_class = original_elem.get("class")
    if orig_class:
        zh_elem.set("class", orig_class)
    zh_elem.set("lang", "zh")
    zh_elem.text = zh_text
    return zh_elem


def process_file(filepath, base_dir, translator, translator_cmd=None, translator_model=None, translator_effort=None):
    relpath = filepath.resolve().relative_to(base_dir.resolve())
    print(f"\n{'='*60}", flush=True)
    print(f"Processing: {relpath}", flush=True)

    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    tree = etree.parse(str(filepath), parser)
    root = tree.getroot()

    elements = collect_translatable_elements(root)
    texts = [get_text(e) for e in elements]

    if not elements:
        print("  No translatable content, skipping.", flush=True)
        return 0, 0, 0

    print(f"  Found {len(texts)} paragraphs to translate", flush=True)
    add_zh_style(tree)

    all_translations = []
    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(texts))
        batch_texts = texts[batch_start:batch_end]

        ctx_start = max(0, batch_start - CONTEXT_BEFORE)
        context_texts = texts[ctx_start:batch_start] if batch_start > 0 else []

        print(f"  Translating batch {batch_start}-{batch_end-1} "
              f"({len(batch_texts)} paragraphs, {len(context_texts)} context)...", flush=True)

        if translator == "claude":
            translations = call_claude_translate(context_texts, batch_texts, model=translator_model)
        elif translator == "codex":
            translations = call_codex_translate(context_texts, batch_texts, model=translator_model, effort=translator_effort)
        else:
            translations = call_custom_translate(context_texts, batch_texts, translator_cmd)
        if translations is None:
            print(f"  [WARN] Batch failed, filling with empty", flush=True)
            translations = [""] * len(batch_texts)

        missing = find_missing_indexes(translations)
        if missing:
            print(f"  [WARN] Missing {len(missing)}/{len(batch_texts)} in batch, auto-retrying...", flush=True)
            for retry_round in range(1, AUTO_RETRY_ROUNDS + 1):
                if not missing:
                    break
                print(f"  [WARN] Retry round {retry_round}/{AUTO_RETRY_ROUNDS}", flush=True)

                for idx in list(missing):
                    global_idx = batch_start + idx
                    single_ctx_start = max(0, global_idx - AUTO_RETRY_CONTEXT)
                    single_ctx_end = global_idx
                    single_context = texts[single_ctx_start:single_ctx_end]

                    single_trans = translate_single_paragraph(
                        single_context,
                        batch_texts[idx],
                        translator,
                        translator_cmd=translator_cmd,
                        translator_model=translator_model,
                    )
                    if not single_trans or is_invalid_translation(single_trans[0] if single_trans else ""):
                        continue
                    translations[idx] = single_trans[0]

                new_missing = find_missing_indexes(translations)
                if len(new_missing) >= len(missing):
                    print(f"  [WARN] Retry round {retry_round} no new gains", flush=True)
                missing = new_missing
                if missing:
                    print(f"  [WARN] Retry {retry_round}: still missing {len(missing)}", flush=True)

        if missing:
            print(f"  [WARN] Batch still has unresolved items: {len(missing)}", flush=True)

        all_translations.extend(translations)

    total = 0
    unresolved = 0
    td_tag = f"{{{XHTML_NS}}}td"
    for elem, zh_text in reversed(list(zip(elements, all_translations))):
        if not zh_text or is_invalid_translation(zh_text):
            if is_invalid_translation(zh_text):
                unresolved += 1
            continue
        parent = elem.getparent()
        if parent is None:
            continue

        if elem.tag == td_tag:
            etree.SubElement(elem, f"{{{XHTML_NS}}}br")
            span = etree.SubElement(elem, f"{{{XHTML_NS}}}span")
            span.set("lang", "zh")
            span.text = zh_text
        else:
            zh_elem = create_zh_element(elem, zh_text)
            idx = list(parent).index(elem)
            parent.insert(idx + 1, zh_elem)
        total += 1

    tree.write(str(filepath), xml_declaration=True, encoding="utf-8", method="xml")
    translated = total
    print(f"  Done: {translated} / {len(elements)} paragraphs translated, {unresolved} unresolved", flush=True)
    return translated, len(elements), unresolved


def create_epub(src_dir, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        mt = src_dir / "mimetype"
        if mt.exists():
            zf.write(str(mt), "mimetype", compress_type=zipfile.ZIP_STORED)

        for root_dir, dirs, files in os.walk(str(src_dir)):
            dirs.sort()
            for f in sorted(files):
                if f == "mimetype":
                    continue
                full = Path(root_dir) / f
                arcname = str(full.relative_to(src_dir))
                zf.write(str(full), arcname)

    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"\nOutput: {output_path}", flush=True)
    print(f"Size: {size_mb:.1f} MB", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Translate epub to bilingual EN-ZH format")
    parser.add_argument("input", help="Input epub file path")
    parser.add_argument("-o", "--output", help="Output epub file path (default: input_bilingual.epub)")
    parser.add_argument("--max-files", type=int, default=0,
                        help="Only translate the first N content files (0 = all)")
    parser.add_argument("--translator", choices=["claude", "codex", "custom"], default=os.environ.get("READ_BOOK_TRANSLATOR", "claude"),
                        help="Translation backend. default: claude (can also set READ_BOOK_TRANSLATOR env var)")
    parser.add_argument("--translator-cmd",
                        help="Shell command for custom translator (required when --translator custom)")
    parser.add_argument("--translator-model",
                        default=os.environ.get("READ_BOOK_TRANSLATOR_MODEL"),
                        help="Model for codex/claude if needed (optional). Use 'latest' for the newest GPT default.")
    parser.add_argument("--translator-effort",
                        default=os.environ.get("READ_BOOK_TRANSLATOR_EFFORT", DEFAULT_CODEX_EFFORT),
                        help="Effort level for GPT/CodeX backends, e.g. low/medium/high")
    args = parser.parse_args()

    translator = args.translator
    translator_cmd = args.translator_cmd or os.environ.get("READ_BOOK_TRANSLATOR_CMD")
    translator_model = args.translator_model

    if translator == "custom" and not translator_cmd:
        print("Error: --translator custom requires --translator-cmd or READ_BOOK_TRANSLATOR_CMD.", file=sys.stderr)
        sys.exit(1)

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = input_path.with_stem(input_path.stem + "_bilingual")

    # Work in temp directory
    work_dir = Path(tempfile.mkdtemp(prefix="epub_translate_"))
    extracted = work_dir / "extracted"

    try:
        # Extract epub
        print(f"Extracting: {input_path.name}", flush=True)
        with zipfile.ZipFile(str(input_path), "r") as zf:
            zf.extractall(str(extracted))

        # Get reading order
        ordered_files = get_reading_order(extracted)
        if args.max_files > 0:
            ordered_files = ordered_files[:args.max_files]

        print(f"Found {len(ordered_files)} content files to process", flush=True)

        total_translated = 0
        total_paragraphs = 0
        total_unresolved = 0
        for fp in ordered_files:
            translated, expected, unresolved = process_file(
                fp,
                extracted,
                translator,
                translator_cmd,
                translator_model,
                args.translator_effort if translator == "codex" else None,
            )
            total_translated += translated
            total_paragraphs += expected
            total_unresolved += unresolved

        print(f"\n{'='*60}", flush=True)
        print(f"Total paragraphs translated: {total_translated}/{total_paragraphs}", flush=True)
        if total_unresolved:
            print(f"  [WARN] Unresolved paragraphs after auto-retry: {total_unresolved}", flush=True)
            print("  [INFO] Output still generated for review/inspection.", flush=True)

        create_epub(extracted, output_path)
        print("Done!", flush=True)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
