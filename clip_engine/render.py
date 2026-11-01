"""Read-only source trimming and Clip2Short portrait rendering with FFmpeg."""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from functools import lru_cache

from PIL import Image

from .artwork import WIDTH, HEIGHT, build_artwork, build_layout, caption_artwork
from .media import _creation_flags, _run_read, extract_frame, find_binary, probe_media


class RenderCancelled(RuntimeError):
    pass


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise RenderCancelled("Rendern abgebrochen.")


def _notify(progress, message, fraction=None):
    if progress is not None:
        progress(message, fraction)


def _number(value):
    return f"{float(value):.9f}"


def _same_file(first: Path, second: Path) -> bool:
    if os.path.normcase(str(first.resolve())) == os.path.normcase(str(second.resolve())):
        return True
    try:
        return first.samefile(second)
    except (OSError, ValueError):
        return False


def _segments(project, metadata):
    raw = project.get("segments", [{"start": 0, "end": metadata["duration"]}])
    if not isinstance(raw, list) or not raw:
        raise ValueError("Mindestens ein Schnitt muss ausgewählt sein.")
    result = []
    for item in raw:
        try:
            start, end = float(item["start"]), float(item["end"])
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("Jeder Schnitt benötigt Start und Ende in Sekunden.") from exc
        if (not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start
                or end > metadata["duration"] + .05):
            raise ValueError("Schnitt liegt außerhalb der Quelle oder hat keine positive Dauer.")
        result.append({"start": start, "end": min(end, metadata["duration"])})
    return result


def map_captions(project: dict, segments: list[dict]) -> list[dict]:
    """Intersect source-relative pages with each cut, then map to the output clock."""
    result = []
    offset = 0.0
    for segment in segments:
        for item in project.get("captions", []):
            try:
                start, end = float(item["start"]), float(item["end"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError("Untertitel benötigen Start, Ende und Text.") from exc
            if not math.isfinite(start) or not math.isfinite(end) or end <= start:
                raise ValueError("Untertitelzeiten sind ungültig.")
            left, right = max(start, segment["start"]), min(end, segment["end"])
            if right > left and str(item.get("text", "")).strip():
                result.append({"start": offset + left - segment["start"],
                               "end": offset + right - segment["start"], "text": str(item["text"])})
        offset += segment["end"] - segment["start"]
    return result


def _caption_at(pages, position):
    active = [(page["start"], index, page["text"]) for index, page in enumerate(pages)
              if page["start"] <= position < page["end"]]
    return max(active)[2] if active else ""


def _cleanup_filter(project, metadata):
    filters = []
    for item in project.get("cleanup_regions", []):
        try:
            values = {key: int(round(float(item[key]))) for key in ("x", "y", "width", "height")}
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Bereinigung benötigt x, y, width und height.") from exc
        x, y, width, height = (values[k] for k in ("x", "y", "width", "height"))
        # delogo needs a one-pixel border from the original image to interpolate.
        if (x < 1 or y < 1 or width < 1 or height < 1 or x + width >= metadata["width"]
                or y + height >= metadata["height"]):
            raise ValueError("Bereinigungsrechtecke benötigen mindestens einen Pixel Abstand zum Quellrand.")
        filters.append(f"delogo=x={x}:y={y}:w={width}:h={height}:show=0")
    return ",".join(filters)


@lru_cache(maxsize=8)
def _check_ffmpeg(binary, cleanup=False):
    filters = _run_read([binary, "-hide_banner", "-filters"]).decode("utf-8", errors="replace")
    needed = ["overlay", "crop", "scale", "concat", "loudnorm"]
    if cleanup:
        needed.append("delogo")
    missing = [name for name in needed if not any(name == token for token in filters.split())]
    if missing:
        raise RuntimeError("Die gefundene FFmpeg-Version ist unvollständig (Filter fehlen: "
                           + ", ".join(missing) + "). Vollständiges FFmpeg von Gyan installieren "
                           "oder CLIP2SHORT_FFMPEG auf die vollständige ffmpeg.exe setzen.")


def _image_input(path: Path, fps: float) -> list[str]:
    return ["-loop", "1", "-framerate", _number(fps), "-i", str(path)]


def _save_artwork(directory, project, layout):
    background, foreground = build_artwork(project, layout)
    background_path, foreground_path = directory / "background.png", directory / "foreground.png"
    background.save(background_path)
    foreground.save(foreground_path)
    return background_path, foreground_path


def _composition_filters(layout, source, base, foreground, captions=None):
    filters = []
    if "facecam" in layout:
        filters.append(f"[{source}]split=2[main_source][camera_source]")
    else:
        filters.append(f"[{source}]null[main_source]")
    previous = f"{base}:v"
    for name, stream in (("main", "main_source"), ("facecam", "camera_source")):
        if name not in layout:
            continue
        target = layout[name]
        crop = target["crop"]
        filters.append(
            f"[{stream}]crop=w={crop['width']}:h={crop['height']}:x={crop['x']}:y={crop['y']}:exact=1,"
            f"scale=w={target['width']}:h={target['height']}:flags=lanczos,setsar=1,format=rgba[{name}_scaled]")
        output = f"with_{name}"
        filters.append(
            f"[{previous}][{name}_scaled]overlay=x={target['x']}:y={target['y']}:"
            f"format=auto:shortest=1:eof_action=pass[{output}]")
        previous = output
    filters.append(f"[{previous}][{foreground}:v]overlay=format=auto:shortest=1:eof_action=pass[art]")
    if captions is not None:
        filters.append(f"[art][{captions}:v]overlay=format=auto:eof_action=pass:repeatlast=1[captioned]")
        previous = "captioned"
    else:
        previous = "art"
    filters.append(f"[{previous}]scale=w=iw:h=ih:out_color_matrix=bt709:out_range=tv,"
                   "setsar=1,format=yuv420p,setparams=colorspace=bt709:"
                   "color_primaries=bt709:color_trc=bt709:range=limited[vout]")
    return filters


def _write_caption_track(directory, project, layout, pages, duration, fps):
    frame_count = max(1, math.ceil(duration * fps - 1e-7))
    quantized = []
    boundaries = {0, frame_count}
    for page in pages:
        left = max(0, min(frame_count, math.ceil(page["start"] * fps - 1e-7)))
        right = max(0, min(frame_count, math.ceil(page["end"] * fps - 1e-7)))
        if right > left:
            quantized.append({"start": left, "end": right, "text": page["text"]})
            boundaries.update((left, right))
    cached = {}
    spans = []
    ordered = sorted(boundaries)
    for left, right in zip(ordered, ordered[1:]):
        text = _caption_at(quantized, left)
        if spans and spans[-1][0] == text:
            spans[-1] = (text, spans[-1][1] + right - left)
        else:
            spans.append((text, right - left))
    lines = ["ffconcat version 1.0"]
    for text, frames in spans:
        if text not in cached:
            name = f"caption-{len(cached):05d}.png"
            caption_artwork(project, layout, text).save(directory / name)
            cached[text] = name
        lines.extend((f"file '{cached[text]}'", f"option framerate {_number(fps)}",
                      f"duration {_number(frames / fps)}"))
    # concat's final duration only takes effect with a final repeated file.
    lines.extend((f"file '{cached[spans[-1][0]]}'", f"option framerate {_number(fps)}"))
    path = directory / "captions.ffconcat"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run_encoder(command, duration, progress=None, cancel=None):
    """Drain both pipes and poll cancellation even when FFmpeg emits no output."""
    _check_cancel(cancel)
    events = queue.Queue()
    stderr_chunks = []
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=_creation_flags())
    except OSError as exc:
        raise RuntimeError(f"FFmpeg konnte nicht gestartet werden: {exc}") from exc

    def read_progress():
        for raw in iter(process.stdout.readline, b""):
            events.put(raw.decode("utf-8", errors="replace").strip())

    def read_errors():
        for raw in iter(lambda: process.stderr.read(4096), b""):
            stderr_chunks.append(raw)
            if sum(map(len, stderr_chunks)) > 64000:
                del stderr_chunks[0]

    readers = [threading.Thread(target=read_progress, daemon=True), threading.Thread(target=read_errors, daemon=True)]
    for reader in readers:
        reader.start()
    last_notify = 0.0
    try:
        while process.poll() is None or not events.empty():
            _check_cancel(cancel)
            try:
                event = events.get(timeout=.1)
            except queue.Empty:
                continue
            if event.startswith("out_time_us="):
                try:
                    fraction = min(.97, max(0, int(event.split("=", 1)[1]) / 1_000_000 / duration * .92 + .04))
                except ValueError:
                    continue
                now = time.monotonic()
                if now - last_notify > .15:
                    _notify(progress, f"Video wird exportiert … {round(fraction * 100)} %", fraction)
                    last_notify = now
        for reader in readers:
            reader.join(timeout=2)
        if process.returncode:
            detail = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()[-10000:]
            raise RuntimeError(f"FFmpeg-Export fehlgeschlagen.\n{detail}")
        _check_cancel(cancel)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for reader in readers:
            reader.join(timeout=2)
        process.stdout.close()
        process.stderr.close()


def preview_project(project: dict, source_time: float, output_path=None) -> Image.Image:
    """Render one composited still with exactly the export's layout and cleanup filters."""
    source = Path(project["source"]).expanduser().resolve()
    position = float(source_time)
    metadata = probe_media(source)
    if not math.isfinite(position) or position < 0 or position >= metadata["duration"]:
        raise ValueError("Die Vorschauposition liegt außerhalb der Quelle.")
    if output_path is not None and _same_file(source, Path(output_path).expanduser().resolve()):
        raise ValueError("Die Vorschau darf die Quelldatei nicht überschreiben.")
    layout = build_layout(project, metadata)
    cleanup = _cleanup_filter(project, metadata)
    binary = find_binary("ffmpeg")
    _check_ffmpeg(binary, bool(cleanup))
    active = _caption_at(project.get("captions", []), position)
    with tempfile.TemporaryDirectory(prefix="clip2short-preview-") as temporary:
        directory = Path(temporary)
        background, foreground = _save_artwork(directory, project, layout)
        caption_path = directory / "caption.png"
        caption_artwork(project, layout, active).save(caption_path)
        command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-filter_complex_threads", "2", "-ss", _number(position), "-i", str(source)]
        for path in (background, foreground, caption_path):
            command.extend(_image_input(path, 30))
        filters = [f"[0:v]setpts=PTS-STARTPTS{',' + cleanup if cleanup else ''}[source]"]
        filters.extend(_composition_filters(layout, "source", 1, 2, 3))
        command.extend(["-filter_complex", ";".join(filters), "-map", "[vout]", "-frames:v", "1",
                        "-an", "-f", "image2pipe", "-c:v", "png", "-threads", "2", "pipe:1"])
        raw = _run_read(command)
        try:
            with Image.open(io.BytesIO(raw)) as image:
                result = image.convert("RGB")
        except OSError as exc:
            raise RuntimeError("Die Vorschau konnte nicht erstellt werden.") from exc
    if output_path is not None:
        destination = Path(output_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".clip2short-preview-", suffix=destination.suffix or ".png",
                                         dir=destination.parent, delete=False) as handle:
            staged = Path(handle.name)
        try:
            result.save(staged)
            os.replace(staged, destination)
        finally:
            staged.unlink(missing_ok=True)
    return result


def render_project(project: dict, progress=None, cancel=None) -> dict:
    _check_cancel(cancel)
    source = Path(project["source"]).expanduser().resolve()
    output = Path(project["output"]).expanduser().resolve()
    if _same_file(source, output):
        raise ValueError("Die Ausgabe darf die Quelldatei nicht überschreiben.")
    if output.suffix.lower() != ".mp4":
        raise ValueError("Die Videoausgabe muss auf .mp4 enden.")
    cover = output.with_suffix(".cover.jpg")
    if _same_file(source, cover):
        raise ValueError("Das Titelbild darf die Quelldatei nicht überschreiben.")
    _notify(progress, "Quelldatei und Bildausschnitte werden geprüft …", 0.0)
    metadata = probe_media(source)
    segments = _segments(project, metadata)
    duration = sum(segment["end"] - segment["start"] for segment in segments)
    fps = float(project.get("fps", 60))
    if not math.isfinite(fps) or not 1 <= fps <= 120:
        raise ValueError("Die Bildrate muss zwischen 1 und 120 liegen.")
    layout = build_layout(project, metadata)
    cleanup = _cleanup_filter(project, metadata)
    pages = map_captions(project, segments)
    binary = find_binary("ffmpeg")
    _check_ffmpeg(binary, bool(cleanup))
    _check_cancel(cancel)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem so the final replacement is atomic.
    with tempfile.TemporaryDirectory(prefix=".clip2short-render-", dir=output.parent) as temporary:
        directory = Path(temporary)
        staged_video, staged_cover = directory / "video.mp4", directory / "cover.jpg"
        background, foreground = _save_artwork(directory, project, layout)
        caption_track = _write_caption_track(directory, project, layout, pages, duration, fps)
        command = [binary, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
                   "-filter_complex_threads", "2", "-progress", "pipe:1", "-nostats"]
        for segment in segments:
            command.extend(["-ss", _number(segment["start"]), "-t", _number(segment["end"] - segment["start"]),
                            "-i", str(source)])
        count = len(segments)
        command.extend(_image_input(background, fps))
        command.extend(_image_input(foreground, fps))
        command.extend(["-f", "concat", "-safe", "0", "-i", str(caption_track)])
        filters = []
        for index, segment in enumerate(segments):
            segment_duration = _number(segment["end"] - segment["start"])
            filters.append(f"[{index}:v]trim=duration={segment_duration},setpts=PTS-STARTPTS,setsar=1[v{index}]")
            if metadata["has_audio"]:
                filters.append(f"[{index}:a:0]atrim=duration={segment_duration},asetpts=PTS-STARTPTS,"
                               f"aresample=48000,aformat=channel_layouts=stereo,apad,"
                               f"atrim=duration={segment_duration}[a{index}]")
            else:
                filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={segment_duration}[a{index}]")
        joined = "".join(f"[v{index}][a{index}]" for index in range(count))
        filters.append(f"{joined}concat=n={count}:v=1:a=1[joined_video][joined_audio]")
        filters.append(f"[joined_video]fps={_number(fps)}{',' + cleanup if cleanup else ''}[source]")
        filters.extend(_composition_filters(layout, "source", count, count + 1, count + 2))
        audio = "loudnorm=I=-16:TP=-1.5:LRA=11," if project.get("normalize_audio", True) else ""
        filters.append(f"[joined_audio]{audio}aresample=48000,aformat=channel_layouts=stereo[aout]")
        # A file avoids the Windows command-line limit with many ordered cuts.
        graph_path = directory / "filters.txt"
        graph_path.write_text(";\n".join(filters), encoding="utf-8")
        command.extend(["-filter_complex_script", str(graph_path), "-map", "[vout]", "-map", "[aout]",
                        "-t", _number(duration), "-r", _number(fps), "-fps_mode", "cfr",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-threads", "8",
                        "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", "-color_range", "tv", "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-ac", "2", "-map_metadata", "-1", "-movflags", "+faststart",
                        str(staged_video)])
        _notify(progress, "Clip2Short-Layout und Untertitel sind vorbereitet …", .03)
        _run_encoder(command, duration, progress, cancel)
        _notify(progress, "Export und Titelbild werden geprüft …", .97)
        result_info = probe_media(staged_video)
        if result_info["width"] != WIDTH or result_info["height"] != HEIGHT:
            raise RuntimeError("FFmpeg hat eine unerwartete Ausgabegröße erzeugt.")
        if abs(result_info["duration"] - duration) > max(.12, 2 / fps):
            raise RuntimeError("Die exportierte Dauer weicht unerwartet vom Schnitt ab.")
        extract_frame(staged_video, 0, WIDTH).save(staged_cover, quality=95, subsampling=0)
        _check_cancel(cancel)
        # Publish the playable video last; failure or cancellation never exposes a partial MP4.
        os.replace(staged_cover, cover)
        os.replace(staged_video, output)
    _notify(progress, "Export abgeschlossen.", 1.0)
    return {"output": str(output), "cover": str(cover), "duration": duration}
