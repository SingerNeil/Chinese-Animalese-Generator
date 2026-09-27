#!/usr/bin/env python3
"""Local-only web interface for the Chinese Animalese Generator."""

from __future__ import annotations

import os
import threading
import time
import uuid
import wave
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_from_directory, url_for

from chinese_animalese import render


ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "output" / "web"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024


def _bounded_float(
    payload: dict[str, Any], key: str, default: float, minimum: float, maximum: float
) -> float:
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{key} 必须是数字") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} 必须在 {minimum} 到 {maximum} 之间")
    return value


def _optional_seed(payload: dict[str, Any]) -> int | None:
    value = payload.get("seed")
    if value in (None, ""):
        return None
    try:
        seed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("变化编号必须是整数") from error
    if not 0 <= seed <= 2_147_483_647:
        raise ValueError("变化编号必须在 0 到 2147483647 之间")
    return seed


def _wav_info(path: Path) -> tuple[float, int]:
    with wave.open(str(path), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    return duration, path.stat().st_size


def _prune_generated_files(limit: int = 50) -> None:
    files = sorted(
        GENERATED_DIR.glob("*.wav"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    for path in files[limit:]:
        path.unlink(missing_ok=True)


@app.after_request
def _disable_generated_audio_cache(response):
    if request.path.startswith(("/audio/", "/download/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify(error="请输入要生成的文字"), 400
    if len(text) > 600:
        return jsonify(error="单次最多生成 600 个字符，请分段处理"), 400

    backend = str(payload.get("backend", "equalo"))
    voice = str(payload.get("voice", "med"))
    dehiss = str(payload.get("dehiss", "remap"))

    try:
        filename = f"animalese-{int(time.time())}-{uuid.uuid4().hex[:8]}.wav"
        output_path = GENERATED_DIR / filename
        render(
            text,
            output_path,
            backend=backend,
            voice=voice,
            dehiss=dehiss,
            speed=_bounded_float(payload, "speed", 1.0, 0.5, 2.0),
            pitch_semitones=_bounded_float(payload, "pitch", 0.0, -8.0, 12.0),
            variation=_bounded_float(payload, "variation", 1.0, 0.0, 2.0),
            pause_scale=_bounded_float(payload, "pauseScale", 1.0, 0.25, 2.5),
            seed=_optional_seed(payload),
        )
        duration, size_bytes = _wav_info(output_path)
        _prune_generated_files()
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as error:
        return jsonify(error=str(error)), 400
    except Exception:
        app.logger.exception("Unexpected generation failure")
        return jsonify(error="生成失败，请查看运行窗口中的错误信息"), 500

    return jsonify(
        filename=filename,
        audioUrl=url_for("audio", filename=filename),
        downloadUrl=url_for("download", filename=filename),
        duration=round(duration, 2),
        sizeBytes=size_bytes,
    )


@app.get("/audio/<path:filename>")
def audio(filename: str):
    return send_from_directory(GENERATED_DIR, filename, mimetype="audio/wav")


@app.get("/download/<path:filename>")
def download(filename: str):
    return send_from_directory(
        GENERATED_DIR,
        filename,
        mimetype="audio/wav",
        as_attachment=True,
        download_name="chinese-animalese.wav",
    )


def main() -> None:
    host = "127.0.0.1"
    port = int(os.environ.get("ANIMALESE_PORT", "7860"))
    url = f"http://{host}:{port}"
    if os.environ.get("ANIMALESE_OPEN_BROWSER") == "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"Chinese Animalese Generator: {url}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()

