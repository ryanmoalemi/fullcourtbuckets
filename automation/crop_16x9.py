"""Crop or pad an image to a true 16:9 file with faces in frame.

Usage: python3 automation/crop_16x9.py IN [OUT] [--pad]
Photos: YuNet face detection (automation/models/) picks the window; faces sit
about a third from the top. --pad (charts, screenshots, cards) keeps the whole
image and fills the sides or top/bottom with the edge colour. Check by eye.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MODEL = Path(__file__).resolve().parent / 'models' / 'face_detection_yunet_2023mar.onnx'


def faces(rgb):
    try:
        import cv2
    except ImportError:
        return []
    h, w = rgb.shape[:2]
    det = cv2.FaceDetectorYN.create(str(MODEL), '', (w, h), 0.6)
    _, found = det.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return [] if found is None else [tuple(int(v) for v in r[:4]) for r in found if r[2] > w / 40]


def to_16x9(im, pad=False):
    im = im.convert('RGB')
    w, h = im.size
    if pad:
        a = np.array(im)
        bg = tuple(int(v) for v in np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0))
        nw, nh = (round(h * 16 / 9), h) if w / h < 16 / 9 else (w, round(w * 9 / 16))
        out = Image.new('RGB', (nw, nh), bg)
        out.paste(im, ((nw - w) // 2, (nh - h) // 2))
        return out
    f = faces(np.array(im))
    if w / h < 16 / 9:
        ch = round(w * 9 / 16)
        y0 = int((min(y for _, y, _, _ in f) + max(y + fh for _, y, _, fh in f)) / 2 - ch * 0.35) if f else int(h * 0.05)
        y0 = max(0, min(h - ch, y0))
        return im.crop((0, y0, w, y0 + ch))
    cw = round(h * 16 / 9)
    cx = sum(x + fw / 2 for x, _, fw, _ in f) / len(f) if f else w / 2
    x0 = max(0, min(w - cw, int(cx - cw / 2)))
    return im.crop((x0, 0, x0 + cw, h))


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--pad']
    src = Path(args[0])
    dst = Path(args[1]) if len(args) > 1 else src
    to_16x9(Image.open(src), '--pad' in sys.argv).save(dst, quality=90)
    print(dst)
