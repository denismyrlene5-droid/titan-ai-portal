from __future__ import annotations
import cv2
import numpy as np

N = 10

def order_points(points: np.ndarray) -> np.ndarray:
    pts = np.asarray(points, dtype=np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )

def perspective_matrix(corners: np.ndarray, size: int = 1000) -> np.ndarray:
    src = order_points(corners)
    dst = np.array([[0, 0], [size-1, 0], [size-1, size-1], [0, size-1]], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)

def warp_board(frame: np.ndarray, matrix: np.ndarray, size: int = 1000) -> np.ndarray:
    return cv2.warpPerspective(frame, matrix, (size, size))

def cell_patch(board: np.ndarray, r: int, c: int, margin: float = 0.22) -> np.ndarray:
    h, w = board.shape[:2]
    ch, cw = h / N, w / N
    x1, x2 = int((c+margin)*cw), int((c+1-margin)*cw)
    y1, y2 = int((r+margin)*ch), int((r+1-margin)*ch)
    return board[y1:y2, x1:x2]

def robust_hsv_color(patch: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    pixels = hsv.reshape(-1, 3).astype(np.float32)
    keep = pixels[pixels[:, 1] > 35]
    if len(keep) < 10:
        keep = pixels
    return np.median(keep, axis=0)

def hsv_distance(a: np.ndarray, b: np.ndarray) -> float:
    dh = min(abs(float(a[0]-b[0])), 180-abs(float(a[0]-b[0]))) / 90.0
    ds = abs(float(a[1]-b[1])) / 255.0
    dv = abs(float(a[2]-b[2])) / 255.0
    return (dh*dh*2.0 + ds*ds + dv*dv) ** 0.5

def classify_board(board: np.ndarray, color_a: np.ndarray, color_b: np.ndarray):
    state = [[0 for _ in range(N)] for _ in range(N)]
    confidences = []

    for r in range(N):
        for c in range(N):
            patch = cell_patch(board, r, c)
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
            sat = float(np.mean(hsv[:, :, 1]))
            val_std = float(np.std(hsv[:, :, 2]))

            if sat < 30 and val_std < 25:
                continue

            sample = robust_hsv_color(patch)
            da, db = hsv_distance(sample, color_a), hsv_distance(sample, color_b)
            nearest = min(da, db)

            if nearest > 0.62:
                continue

            state[r][c] = 1 if da < db else 2
            confidences.append(max(0.0, 1.0-nearest))

    return state, float(np.mean(confidences)) if confidences else 0.0

def board_difference(a, b) -> int:
    return sum(a[r][c] != b[r][c] for r in range(N) for c in range(N))

def draw_state(board_img: np.ndarray, state):
    out = board_img.copy()
    h, w = out.shape[:2]
    ch, cw = h / N, w / N
    for r in range(N):
        for c in range(N):
            if not state[r][c]:
                continue
            center = (int((c+.5)*cw), int((r+.5)*ch))
            cv2.circle(out, center, int(min(cw, ch)*.34), (255,255,255), 3)
            cv2.putText(out, str(state[r][c]), center, cv2.FONT_HERSHEY_SIMPLEX, .8, (255,255,255), 2)
    return out


def auto_detect_board(frame: np.ndarray):
    """
    Attempts to find the largest near-square quadrilateral in the frame.
    Returns four corner points or None. Manual calibration remains available.
    """
    resized = frame.copy()
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(gray, 40, 130)
    edges = cv2.dilate(edges, None, iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = frame.shape[0] * frame.shape[1]
    candidates = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < frame_area * 0.12:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * peri, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue

        pts = approx.reshape(4, 2).astype(np.float32)
        ordered = order_points(pts)
        widths = [
            np.linalg.norm(ordered[1] - ordered[0]),
            np.linalg.norm(ordered[2] - ordered[3]),
        ]
        heights = [
            np.linalg.norm(ordered[3] - ordered[0]),
            np.linalg.norm(ordered[2] - ordered[1]),
        ]
        mean_w, mean_h = np.mean(widths), np.mean(heights)
        ratio = mean_w / max(mean_h, 1)
        if not 0.70 <= ratio <= 1.30:
            continue
        candidates.append((area, ordered))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]
