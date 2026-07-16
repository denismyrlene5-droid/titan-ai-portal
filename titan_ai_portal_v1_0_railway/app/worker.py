from __future__ import annotations
import csv
import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

from .rules import infer_move
from .db import update_job
from .vision import perspective_matrix, warp_board, classify_board, board_difference, draw_state

def stable_candidate(history, required=4):
    if len(history) < required:
        return None
    recent = history[-required:]
    base = recent[0][0]
    if all(board_difference(base, item[0]) <= 1 for item in recent[1:]):
        return max(recent, key=lambda x: x[1])
    return None

def download_youtube(url: str, job_dir: Path) -> Path:
    target = job_dir / "source_video.%(ext)s"
    cmd = ["yt-dlp", "-f", "best[ext=mp4]/best", "-o", str(target), url]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    matches = list(job_dir.glob("source_video.*"))
    if not matches:
        raise RuntimeError("Video download did not produce a file.")
    return matches[0]

def create_calibration_frame(video_path: Path, job_dir: Path):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Could not open uploaded video.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = frames / fps if fps else 0
    cap.set(cv2.CAP_PROP_POS_MSEC, min(5000, duration*1000*.1))
    ok, frame = cap.read()
    cap.release()

    if not ok:
        raise RuntimeError("Could not read a calibration frame.")

    path = job_dir / "calibration.jpg"
    cv2.imwrite(str(path), frame)
    return path

def process_video(job_dir: Path, calibration: dict, sample_fps: float = 3.0):
    meta = json.loads((job_dir / "meta.json").read_text())
    video_path = Path(meta["video_path"])
    job_id = job_dir.name

    def update(stage, progress, message, summary=None):
        update_job(job_id, stage, progress, message, summary)

    update("processing", 2, "Opening video")

    corners = np.array(calibration["corners"], dtype=np.float32)
    color_a = np.array(calibration["color_a"], dtype=np.float32)
    color_b = np.array(calibration["color_b"], dtype=np.float32)
    matrix = perspective_matrix(corners)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Cannot open video.")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_step = max(1, int(round(fps / sample_fps)))

    positions_dir = job_dir / "positions"
    uncertain_dir = job_dir / "uncertain"
    positions_dir.mkdir(exist_ok=True)
    uncertain_dir.mkdir(exist_ok=True)

    history, accepted_states, moves, uncertain = [], [], [], []
    last_state = None
    player_to_move = 1
    frame_index = 0
    accepted_index = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_index % frame_step:
            frame_index += 1
            continue

        board_img = warp_board(frame, matrix)
        state, confidence = classify_board(board_img, color_a, color_b)
        history.append((state, confidence, board_img.copy(), frame_index / fps))
        history = history[-6:]

        stable = stable_candidate(history)
        if stable:
            state, conf, stable_img, timestamp = stable
            if last_state is None or board_difference(last_state, state) >= 2:
                if last_state is not None:
                    inferred = infer_move(last_state, state, player_to_move)
                    if inferred:
                        moves.append({
                            "move_number": len(moves)+1,
                            "player": inferred.player,
                            "start": list(inferred.start),
                            "end": list(inferred.end),
                            "captures": [list(x) for x in inferred.captures],
                            "promoted": inferred.promoted,
                            "confidence": round(min(conf, inferred.confidence), 3),
                            "timestamp_seconds": round(timestamp, 2),
                        })
                        player_to_move = 2 if player_to_move == 1 else 1
                    else:
                        uncertain.append({
                            "timestamp_seconds": round(timestamp, 2),
                            "difference_count": board_difference(last_state, state),
                            "confidence": round(conf, 3),
                        })
                        cv2.imwrite(str(uncertain_dir / f"uncertain_{len(uncertain):04d}.jpg"), stable_img)

                accepted_states.append({
                    "index": accepted_index,
                    "timestamp_seconds": round(timestamp, 2),
                    "confidence": round(conf, 3),
                    "board": state,
                })

                annotated = draw_state(stable_img, state)
                cv2.imwrite(str(positions_dir / f"position_{accepted_index:04d}.jpg"), annotated)
                accepted_index += 1
                last_state = [row[:] for row in state]

        frame_index += 1
        if frame_count:
            pct = min(95, 5 + int(frame_index / frame_count * 90))
            if frame_index % max(frame_step*20, 1) == 0:
                update("processing", pct, f"Analyzing frame {frame_index:,} of {frame_count:,}")

    cap.release()

    game = {
        "board_size": 10,
        "positions": accepted_states,
        "moves": moves,
        "uncertain_positions": uncertain,
        "notes": [
            "Piece values: 0 empty, 1 Player A, 2 Player B, 3 Player A king, 4 Player B king.",
            "King detection is not automatic in v0.1.",
        ],
    }
    (job_dir / "game.json").write_text(json.dumps(game, indent=2), encoding="utf-8")

    with (job_dir / "moves.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "move_number","player","start","end","captures","promoted","confidence","timestamp_seconds"
        ])
        writer.writeheader()
        for move in moves:
            row = move.copy()
            row["start"] = str(row["start"])
            row["end"] = str(row["end"])
            row["captures"] = str(row["captures"])
            writer.writerow(row)

    zip_base = job_dir / "titan_analysis"
    shutil.make_archive(str(zip_base), "zip", root_dir=job_dir)

    summary = {
        "positions_detected": len(accepted_states),
        "moves_inferred": len(moves),
        "uncertain_positions": len(uncertain),
    }
    (job_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    update("complete", 100, "Analysis complete", summary)
