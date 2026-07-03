#!/usr/bin/env python3
"""
OCR a WeChat chat screenshot and output text with positions.

Usage:
    # Full image
    python ocr_chat.py /tmp/screenshot.png

    # Crop to chat area first (x1,y1,x2,y2 in image pixels)
    python ocr_chat.py /tmp/screenshot.png --crop 1760,100,2400,1400

Output: one JSON line per text block, sorted top-to-bottom:
    {"y": 123, "x": 45, "text": "你好", "score": 0.98}

Requires: paddlepaddle + paddleocr installed in the venv at /tmp/paddleocr-venv
"""

import argparse
import json
import os
import sys

os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["GLOG_minloglevel"] = "2"

import warnings
warnings.filterwarnings("ignore")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="Path to screenshot")
    parser.add_argument("--crop", help="Crop region: x1,y1,x2,y2")
    args = parser.parse_args()

    from PIL import Image
    img_path = args.image

    if args.crop:
        x1, y1, x2, y2 = [int(v) for v in args.crop.split(",")]
        img = Image.open(img_path)
        cropped = img.crop((x1, y1, x2, y2))
        img_path = img_path.rsplit(".", 1)[0] + "_cropped.png"
        cropped.save(img_path)

    from paddleocr import PaddleOCR
    ocr = PaddleOCR(ocr_version="PP-OCRv4", lang="ch")
    result = ocr.predict(img_path)

    items = []
    for res in result:
        if "rec_texts" not in res:
            continue
        for i, text in enumerate(res["rec_texts"]):
            score = float(res["rec_scores"][i])
            if score < 0.5 or not text.strip():
                continue
            poly = res["dt_polys"][i]
            x_min = int(min(p[0] for p in poly))
            y_min = int(min(p[1] for p in poly))
            items.append({
                "y": y_min,
                "x": x_min,
                "text": text.strip(),
                "score": round(score, 3),
            })

    for item in sorted(items, key=lambda d: (d["y"], d["x"])):
        print(json.dumps(item, ensure_ascii=False))


if __name__ == "__main__":
    main()
