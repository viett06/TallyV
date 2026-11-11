"""Local background features for the MobileNetV2 ONNX Model Zoo checkpoint."""

from functools import lru_cache
from hashlib import file_digest
from io import BytesIO
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings

MODEL_SHA256 = "c0c3f76d93fa3fd6580652a45618618a220fced18babf65774ed169de0432ad5"
FEATURE_VERSION = "mobilenetv2-12-background-v1"
_POOL = "onnx_node!GlobalAveragePool_97"
_NETWORK_LOCK = Lock()


@lru_cache(maxsize=1)
def _network(path: Path, modified_ns: int, size: int):
    with path.open("rb") as model:
        if file_digest(model, "sha256").hexdigest() != MODEL_SHA256:
            raise ValueError("Unexpected MobileNetV2 checkpoint")
    return cv2.dnn.readNetFromONNX(str(path))


def embedding(background: np.ndarray) -> list[float]:
    path = settings.evidence_history_model_path
    if path is None:
        raise ValueError("Missing EVIDENCE_HISTORY_MODEL_PATH")
    stat = path.stat()
    rgb = cv2.resize(background, (224, 224), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    rgb = (rgb - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    with _NETWORK_LOCK:
        net = _network(path, stat.st_mtime_ns, stat.st_size)
        net.setInput(np.ascontiguousarray(rgb.transpose(2, 0, 1)[None]))
        vector = net.forward(_POOL).reshape(-1)
    norm = np.linalg.norm(vector)
    if vector.size != 1280 or not np.isfinite(norm) or norm <= 0:
        raise ValueError("Invalid MobileNetV2 embedding")
    return (vector / norm).tolist()


@lru_cache(maxsize=2)
def _face_detector(cascade):
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + cascade)
    if detector.empty():
        raise ValueError("Missing OpenCV face detector")
    return detector


def _gray(image):
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def fingerprint(image: Image.Image) -> bytes:
    gray = image.convert("L")
    low_frequency = cv2.dct(np.asarray(gray.resize((32, 32)), dtype=np.float32))[:8, :8].ravel()[1:]
    reduced = np.asarray(gray.resize((17, 17)))
    return b"".join(
        np.packbits(bits).tobytes()
        for bits in (
            low_frequency > np.median(low_frequency),
            reduced[:16, 1:] > reduced[:16, :-1],
            reduced[1:, :16] > reduced[:-1, :16],
        )
    )


def near_duplicate(first: bytes, second: bytes) -> bool:
    if len(first) != 72 or len(second) != 72:
        return False
    first_bits, second_bits = int.from_bytes(first, "big"), int.from_bytes(second, "big")
    gradient_mask = (1 << 512) - 1
    if min((first_bits & gradient_mask).bit_count(), (second_bits & gradient_mask).bit_count()) < 24:
        return False
    difference = first_bits ^ second_bits
    return difference.bit_count() <= 24 and (difference >> 512).bit_count() <= 4


def open_image(content: bytes) -> Image.Image:
    with Image.open(BytesIO(content)) as image:
        return image.convert("RGB")


def background(image: Image.Image, extracted: dict):
    kind = extracted.get("kind")
    image = image.copy()
    image.thumbnail((720, 720))
    rgb = np.array(image)
    height, width = rgb.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[round(height * 0.08) : round(height * 0.92), round(width * 0.08) : round(width * 0.92)] = 255
    scene = extracted.get("scene", {}).get("kind")
    face_evidence = scene == "FACE" or "RECOGNIZED" in extracted.get("observed_states", [])
    faces = _face_boxes(_gray(rgb), face_evidence)
    if face_evidence and not faces:
        return None
    if kind in {"ATTENDANCE", "LEAVE"} and scene != "WORK_AREA" and not faces:
        return None
    for x, y, w, h in faces:
        mask[max(0, y - h // 2) : y + h + h // 3, max(0, x - w // 3) : x + w + w // 3] = 0

    if scene == "DEVICE" or kind == "DEVICE":
        mask[height // 5 : height * 4 // 5, width // 5 : width * 4 // 5] = 0
    for region in extracted.get("ocr_regions", []):
        x1, y1, x2, y2 = region["box"]
        mask[max(0, int(y1 * height) - 4) : int(y2 * height) + 4, max(0, int(x1 * width) - 4) : int(x2 * width) + 4] = 0
    if np.count_nonzero(mask) < width * height * 0.14:
        return None
    # Keep image dimensions and suppress sharp edges introduced by masking in feature detection.
    rgb[mask == 0] = (124, 116, 104)
    inner_mask = cv2.erode(mask, np.ones((17, 17), np.uint8))
    points, descriptors = cv2.SIFT_create(nfeatures=700).detectAndCompute(_gray(rgb), inner_mask)
    if descriptors is None or len(points) < 20:
        return None
    xy = np.array([point.pt for point in points], dtype=np.float32)
    if _coverage(xy, rgb.shape) < 0.035 or len(_regions(xy, rgb.shape)) < 3:
        return None
    return rgb, xy, descriptors


def _face_boxes(gray, use_profile):
    parameters = {"scaleFactor": 1.08, "minNeighbors": 4, "minSize": (28, 28)}
    with _NETWORK_LOCK:
        frontal = _face_detector("haarcascade_frontalface_default.xml")
        faces = list(frontal.detectMultiScale(gray, **parameters))
        if use_profile and not faces:
            profile = _face_detector("haarcascade_profileface.xml")
            faces.extend(profile.detectMultiScale(gray, **parameters))
            width = gray.shape[1]
            faces.extend(
                (width - x - w, y, w, h) for x, y, w, h in profile.detectMultiScale(cv2.flip(gray, 1), **parameters)
            )
    return faces


def _coverage(points, shape):
    height, width = shape[:2]
    return cv2.contourArea(cv2.convexHull(points)) / (height * width)


def _regions(points, shape):
    height, width = shape[:2]
    return sorted({int(x >= width / 2) + 2 * int(y >= height / 2) for x, y in points})


def geometry(query, reference) -> dict | None:
    first, first_points, first_descriptors = query
    second, second_points, second_descriptors = reference
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    pairs = matcher.knnMatch(first_descriptors, second_descriptors, k=2)
    reverse = matcher.knnMatch(second_descriptors, first_descriptors, k=2)
    reverse_best = {a.queryIdx: a.trainIdx for a, b in reverse if a.distance < 0.75 * b.distance}
    matches = [a for a, b in pairs if a.distance < 0.75 * b.distance and reverse_best.get(a.trainIdx) == a.queryIdx]
    if len(matches) < 7:
        return None
    source = first_points[[m.queryIdx for m in matches]]
    target = second_points[[m.trainIdx for m in matches]]
    transform, mask = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC, ransacReprojThreshold=4)
    if transform is None or mask is None:
        return None
    scale = float(np.hypot(*transform[:, 0]))
    if not 0.35 <= scale <= 3:
        return None
    accepted = mask.ravel().astype(bool)
    count = int(accepted.sum())
    regions = _regions(source[accepted], first.shape) if count else []
    coverage = min(_coverage(source[accepted], first.shape), _coverage(target[accepted], second.shape)) if count else 0
    if count < 7 or count / len(matches) < 0.45 or coverage < 0.008:
        return None
    strong = count >= 14 and count / len(matches) >= 0.60 and coverage >= 0.035 and len(regions) >= 3
    return {"strength": "STRONG" if strong else "PARTIAL", "feature_count": count, "regions": regions}
