"""Read-only media access and discovery of a complete FFmpeg installation."""
from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from fractions import Fraction

from PIL import Image


def _creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def find_binary(name: str) -> str:
    """Find FFmpeg/FFprobe without depending on a Node or Remotion runtime."""
    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError("Nur ffmpeg und ffprobe werden unterstützt.")
    override = os.environ.get(f"CLIP2SHORT_{name.upper()}")
    executable = name + (".exe" if os.name == "nt" else "")
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return str(path.resolve())
        raise RuntimeError(f"CLIP2SHORT_{name.upper()} verweist auf keine Datei: {override}")
    candidates: list[Path] = []
    on_path = shutil.which(name)
    if on_path:
        candidates.append(Path(on_path))
    package = Path(__file__).resolve().parent
    for root in (package / "bin", package.parent / "bin"):
        candidates.append(root / executable)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        local_path = Path(local)
        candidates.append(local_path / "Microsoft" / "WinGet" / "Links" / executable)
        winget = local_path / "Microsoft" / "WinGet" / "Packages"
        if winget.is_dir():
            for root in sorted(winget.glob("*FFmpeg*"), reverse=True):
                candidates.extend(sorted(root.glob(f"*/bin/{executable}")))
                candidates.extend(sorted(root.glob(f"bin/{executable}")))
        candidates.extend(sorted((local_path / "Programs").glob(f"*ffmpeg*/bin/{executable}")))
    for path in candidates:
        # Remotion ships a restricted binary without overlay and delogo.
        if path.is_file() and "remotion" not in str(path).lower():
            return str(path.resolve())
    raise RuntimeError(
        f"{name} fehlt. Vollständiges FFmpeg installieren: "
        "winget install --id Gyan.FFmpeg --exact . Danach die Anwendung neu starten. "
        f"Alternativ {executable} in den bin-Ordner der Anwendung legen."
    )


def _run_read(command: list[str], timeout: float = 90) -> bytes:
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=timeout,
            creationflags=_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Das Lesen der Mediendatei hat zu lange gedauert.") from exc
    except OSError as exc:
        raise RuntimeError(f"Medienwerkzeug konnte nicht gestartet werden: {exc}") from exc
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-5000:]
        raise RuntimeError(f"Mediendatei konnte nicht gelesen werden.\n{detail}")
    return result.stdout


def probe_media(path: str | os.PathLike[str]) -> dict:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError(f"Quelldatei fehlt: {source}")
    raw = _run_read([
        find_binary("ffprobe"), "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(source),
    ])
    try:
        data = json.loads(raw)
        videos = [s for s in data.get("streams", []) if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")]
        if not videos:
            raise ValueError("Die Datei enthält keine Videospur.")
        video = videos[0]
        width, height = int(video["width"]), int(video["height"])
        rotation = 0
        for item in video.get("side_data_list", []):
            if "rotation" in item:
                rotation = int(round(float(item["rotation"]))) % 360
        if not rotation:
            rotation = int(float(video.get("tags", {}).get("rotate", 0))) % 360
        if rotation in (90, 270):
            width, height = height, width
        duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
        fps_text = video.get("avg_frame_rate", "0/1")
        if not fps_text or fps_text == "0/0":
            fps_text = video.get("r_frame_rate", "0/1")
        fps = float(Fraction(fps_text))
        if width <= 0 or height <= 0 or duration <= 0 or not math.isfinite(duration):
            raise ValueError("Bildgröße oder Videodauer ist ungültig.")
        return {"width": width, "height": height, "duration": duration,
                "fps": fps if fps > 0 and math.isfinite(fps) else 30.0,
                "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", []))}
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        raise RuntimeError(f"Ungültige Medieninformationen: {exc}") from exc


def extract_frame(path: str | os.PathLike[str], time_seconds: float, width: int = 960) -> Image.Image:
    if not math.isfinite(float(time_seconds)) or time_seconds < 0:
        raise ValueError("Die Bildposition muss eine nichtnegative Sekundenzahl sein.")
    if not isinstance(width, int) or isinstance(width, bool) or width < 1 or width > 16384:
        raise ValueError("Die Vorschaubreite muss zwischen 1 und 16384 liegen.")
    raw = _run_read([
        find_binary("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
        "-ss", f"{float(time_seconds):.9f}", "-i", str(Path(path).expanduser().resolve()),
        "-map", "0:v:0", "-frames:v", "1", "-vf", f"scale={width}:-1:flags=lanczos",
        "-f", "image2pipe", "-c:v", "png", "pipe:1",
    ])
    try:
        with Image.open(io.BytesIO(raw)) as frame:
            return frame.convert("RGB")
    except (OSError, ValueError) as exc:
        raise RuntimeError("An dieser Position konnte kein Videobild gelesen werden.") from exc
