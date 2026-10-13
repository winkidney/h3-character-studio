"""Analytic vector geometry extracted from the HD2D character normal tool."""
import math
import cv2
import numpy as np
SIZE=256
YY,XX=np.mgrid[0:SIZE,0:SIZE].astype(np.float32)
GRID=np.stack((XX,YY),axis=-1)

def unit(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-8)

def optical_flow(frames: list[np.ndarray]) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Diffuse channels are correspondence features only, never elevation."""
    grays = []
    for im in frames:
        g = cv2.cvtColor(im[..., :3], cv2.COLOR_RGB2GRAY)
        g[im[..., 3] == 0] = 0
        grays.append(g)
    forward, backward = [], []
    for i, gray in enumerate(grays):
        other = grays[(i + 1) % len(grays)]
        forward.append(cv2.calcOpticalFlowFarneback(gray, other, None, 0.5, 4, 17, 4, 7, 1.5, 0))
        backward.append(cv2.calcOpticalFlowFarneback(other, gray, None, 0.5, 4, 17, 4, 7, 1.5, 0))
    return forward, backward

def sample_flow(flow: np.ndarray, point: list[float]) -> np.ndarray:
    # Local median is stable on narrow braid segments and tassels.
    x, y = np.rint(point).astype(int)
    x, y = np.clip(x, 2, 253), np.clip(y, 2, 253)
    return np.median(flow[y - 2:y + 3, x - 2:x + 3].reshape(-1, 2), axis=0)

def ellipse_region(spec: list[float], scale=1.0) -> np.ndarray:
    cx, cy, rx, ry = spec
    return ((XX - cx) / (rx * scale)) ** 2 + ((YY - cy) / (ry * scale)) ** 2 <= 1

def tube_geometry(points: list[list[float]], radius: float, amplitude=0.72, braid=False) -> tuple[np.ndarray, np.ndarray]:
    """Analytic cylinder following the drawn polyline, optionally braided."""
    distance2 = np.full((SIZE, SIZE), np.inf, np.float32)
    radial = np.zeros((SIZE, SIZE, 2), np.float32)
    station = np.zeros((SIZE, SIZE), np.float32)
    arc = 0.0
    for pa, pb in zip(points, points[1:]):
        a, b = np.array(pa, np.float32), np.array(pb, np.float32)
        axis = b - a
        length = max(float(np.linalg.norm(axis)), 0.1)
        t = np.clip(((GRID - a) * axis).sum(-1) / (length * length), 0, 1)
        q = a + t[..., None] * axis
        delta = GRID - q
        d2 = (delta * delta).sum(-1)
        pick = d2 < distance2
        distance2[pick] = d2[pick]
        radial[pick] = delta[pick] / radius
        station[pick] = arc + t[pick] * length
        arc += length
    xy = radial * amplitude
    if braid:
        phase = station * (2 * math.pi / 9.0)
        xy[..., 0] += np.sin(phase) * 0.18
        xy[..., 1] += np.cos(phase) * 0.12
    xy[..., 1] *= -1  # original image Y grows down, tangent Y points up.
    z = np.sqrt(np.maximum(0.16, 1 - (xy * xy).sum(-1)))
    n = unit(np.dstack((xy, z)))
    return distance2 <= (radius * 1.45) ** 2, n

def ellipsoid(spec: list[float], slope=0.65, yaw=0.0) -> np.ndarray:
    cx, cy, rx, ry = spec
    x = np.clip((XX - cx) / rx, -1.15, 1.15) * slope + yaw
    y = np.clip(-(YY - cy) / ry, -1.15, 1.15) * slope
    z = np.sqrt(np.maximum(0.22, 1 - x*x - y*y))
    return unit(np.dstack((x, y, z)))
