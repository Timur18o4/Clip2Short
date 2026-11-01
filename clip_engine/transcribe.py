"""Local, editable source-timed captions made with faster-whisper.

Only the selected source ranges are extracted. Neither this module nor the
caption cache changes the original video. Model imports are deliberately lazy
so the editor and renderer work without the optional transcription dependency.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Callable


Progress = Callable[[str, float | None], None]
_CACHE_VERSION = 2
_MAX_PAGE_SECONDS = 2.0
_MAX_PAGE_WORDS = 7


class TranscriptionCancelled(RuntimeError):
    """The worker was cancelled before its result was committed."""


def _report(progress: Progress | None, message: str, fraction: float | None = None) -> None:
    if progress is not None:
        progress(message, fraction)


def _check_cancel(cancel: Any) -> None:
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("Transkription abgebrochen.")


def _user_cache_dir() -> Path:
    from cng_clip_service.config import data_dir
    return data_dir() / 'transcripts'


def _probe_source(source: Path) -> dict:
    from .media import probe_media

    return probe_media(str(source))


def _fingerprint(source: Path, cancel: Any = None) -> dict:
    """Hash every byte; even an edit retaining size and mtime invalidates cache."""
    before = source.stat()
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            _check_cancel(cancel)
            digest.update(chunk)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("Die Quelldatei wurde während der Prüfung geändert. Transkription erneut starten.")
    return {
        "path": os.path.normcase(str(source.resolve())),
        "size": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def _cache_path(metadata: dict) -> Path:
    serialized = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return _user_cache_dir() / f"{key}.cng-transcript.json"


def _valid_pages(pages: Any, ranges: list[dict]) -> bool:
    if not isinstance(pages, list):
        return False
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("text"), str) or not page["text"].strip():
            return False
        try:
            start, end = float(page["start"]), float(page["end"])
        except (KeyError, ValueError, TypeError):
            return False
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            return False
        if end - start > _MAX_PAGE_SECONDS + 0.001:
            return False
        if not any(start >= part["start"] - 0.001 and end <= part["end"] + 0.001 for part in ranges):
            return False
        if "confidence" in page:
            try:
                confidence = float(page["confidence"])
            except (ValueError, TypeError):
                return False
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                return False
    return True


def _read_cache(path: Path, metadata: dict, ranges: list[dict]) -> list[dict] | None:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(content, dict) or content.get("metadata") != metadata:
        return None
    pages = content.get("pages")
    return pages if _valid_pages(pages, ranges) else None


def _write_cache(path: Path, metadata: dict, pages: list[dict], cancel: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"metadata": metadata, "pages": pages}, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        _check_cancel(cancel)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _hub_cache_roots() -> list[Path]:
    roots: list[Path] = []
    for key in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]).expanduser())
    if os.environ.get("HF_HOME"):
        roots.append(Path(os.environ["HF_HOME"]).expanduser() / "hub")
    if os.environ.get("XDG_CACHE_HOME"):
        roots.append(Path(os.environ["XDG_CACHE_HOME"]).expanduser() / "huggingface" / "hub")
    # Hugging Face's installed configuration also accounts for its defaults.
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        roots.append(Path(HF_HUB_CACHE))
    except ImportError:
        pass
    roots.append(Path.home() / ".cache" / "huggingface" / "hub")
    return list(dict.fromkeys(roots))


def _find_cached_model(model_name: str) -> Path | None:
    supplied = Path(model_name).expanduser()
    if supplied.is_dir():
        if not all((supplied / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
            raise RuntimeError(f"Im Modellordner fehlen model.bin, config.json oder tokenizer.json: {supplied}")
        return supplied
    if "/" in model_name:
        repo = model_name
    elif model_name == "large":
        repo = "Systran/faster-whisper-large-v3"
    elif model_name in {"tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v1", "large-v2", "large-v3"}:
        repo = f"Systran/faster-whisper-{model_name}"
    else:
        # Let faster-whisper resolve its remaining supported aliases locally.
        return None
    folder_name = "models--" + repo.replace("/", "--")
    for root in _hub_cache_roots():
        folder = root / folder_name
        candidates: list[Path] = []
        try:
            reference = (folder / "refs" / "main").read_text(encoding="utf-8").strip()
            if reference and Path(reference).name == reference:
                candidates.append(folder / "snapshots" / reference)
        except OSError:
            pass
        snapshots = folder / "snapshots"
        if snapshots.is_dir():
            try:
                candidates.extend(sorted(snapshots.iterdir(), key=lambda path: path.stat().st_mtime_ns, reverse=True))
            except OSError:
                continue
        for candidate in candidates:
            if all((candidate / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
                return candidate
    return None


def _load_model(model_name: str, progress: Progress | None, cancel: Any):
    _check_cancel(cancel)
    try:
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
    except ImportError as exc:
        raise RuntimeError("Spracherkennung fehlt. Im Programmordner INSTALLIEREN.cmd ausführen (Paket faster-whisper).") from exc
    local = _find_cached_model(model_name)
    _report(progress, f"Lade Sprachmodell {model_name} lokal (CPU/int8).", None)
    if local is None:
        try:
            local = Path(download_model(model_name, local_files_only=True))
            # Incomplete snapshots must not cause the tokenizer to silently
            # download behind the caller's back during WhisperModel loading.
            if not all((local / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
                local = None
        except Exception as exc:
            missing = isinstance(exc, FileNotFoundError) or type(exc).__name__ == "LocalEntryNotFoundError"
            if not missing:
                raise RuntimeError(f"Sprachmodell {model_name} kann nicht lokal gefunden werden: {exc}") from exc
        if local is None:
            _check_cancel(cancel)
            _report(progress, f"Sprachmodell {model_name} ist nicht vollständig lokal vorhanden. Download startet; Internet und freier Speicher werden benötigt.", None)
            try:
                local = Path(download_model(model_name, local_files_only=False))
            except Exception as download_error:
                raise RuntimeError(f"Sprachmodell konnte nicht heruntergeladen werden: {download_error}") from download_error
    _check_cancel(cancel)
    if not all((local / name).is_file() for name in ("model.bin", "config.json", "tokenizer.json")):
        raise RuntimeError(f"Sprachmodell ist unvollständig (model.bin/config.json/tokenizer.json): {local}")
    try:
        model = WhisperModel(str(local), device="cpu", compute_type="int8", local_files_only=True)
    except Exception as exc:
        raise RuntimeError(f"Das lokale Sprachmodell kann nicht geladen werden: {exc}") from exc
    _check_cancel(cancel)
    return model


def _extract_audio(source: Path, start: float, end: float, destination: Path, cancel: Any) -> None:
    from .media import find_binary

    command = [find_binary("ffmpeg"), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
               "-ss", f"{start:.9f}", "-i", str(source), "-t", f"{end-start:.9f}",
               "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(destination)]
    with tempfile.TemporaryFile() as errors:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors, creationflags=flags)
        try:
            while process.poll() is None:
                _check_cancel(cancel)
                time.sleep(0.1)
            _check_cancel(cancel)
            if process.returncode:
                errors.seek(0)
                detail = errors.read().decode("utf-8", errors="replace").strip()[-2000:]
                raise RuntimeError(f"Die Tonspur konnte nicht extrahiert werden: {detail or 'FFmpeg meldet einen Fehler.'}")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


def _join_words(words: list[dict]) -> str:
    text = " ".join(word["text"].strip() for word in words)
    text = re.sub(r"\s+([,.;:!?%\)\]\}])", r"\1", text)
    text = re.sub(r"([\(\[\{])\s+", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _make_pages(words: list[dict], offset: float, range_end: float) -> list[dict]:
    pages: list[dict] = []
    pending: list[dict] = []

    def flush() -> None:
        if not pending:
            return
        start = max(offset, offset + pending[0]["start"])
        end = min(range_end, offset + pending[-1]["end"], start + _MAX_PAGE_SECONDS)
        text = _join_words(pending)
        if text and end > start:
            page: dict = {"start": round(start, 6), "end": round(end, 6), "text": text}
            probabilities = [word["confidence"] for word in pending if word.get("confidence") is not None]
            if probabilities:
                page["confidence"] = round(sum(probabilities) / len(probabilities), 3)
            pages.append(page)
        pending.clear()

    for word in words:
        if pending:
            count = sum(len(item["text"].split()) for item in pending)
            incoming_count = len(word["text"].split())
            too_long = word["end"] - pending[0]["start"] > _MAX_PAGE_SECONDS + 1e-8
            pause = word["start"] - pending[-1]["end"] >= 0.45
            punctuation = re.search(r"[.!?;:][\"'”’)]*$", pending[-1]["text"])
            if too_long or count + incoming_count > _MAX_PAGE_WORDS or (count >= 3 and (pause or punctuation)):
                flush()
        pending.append(word)
    flush()
    return pages


def _segment_words(segment: Any, duration: float) -> list[dict]:
    """Use aligned words and do not invent missing word times."""
    result: list[dict] = []
    aligned = getattr(segment, "words", None)
    if aligned:
        for word in aligned:
            text = str(getattr(word, "word", "")).strip()
            try:
                start, end = float(word.start), float(word.end)
            except (AttributeError, TypeError, ValueError):
                continue
            if not text or not math.isfinite(start) or not math.isfinite(end):
                continue
            start, end = max(0.0, start), min(duration, end)
            if end <= start:
                continue
            try:
                probability = float(getattr(word, "probability", None))
                confidence = max(0.0, min(1.0, probability)) if math.isfinite(probability) else None
            except (TypeError, ValueError):
                confidence = None
            result.append({"start": start, "end": end, "text": text, "confidence": confidence})
        return result
    # Word timestamps are required for trustworthy short pages. A segment with
    # text but no alignment is surfaced as an error rather than invented timing.
    if str(getattr(segment, "text", "")).strip():
        raise RuntimeError("Die Spracherkennung lieferte Text ohne Wort-Zeitmarken. Transkription erneut starten oder Untertitel manuell eintragen.")
    return result


def transcribe_project(project: dict, progress: Progress | None = None, cancel: Any = None) -> list[dict]:
    """Return editable caption pages in original source seconds.

    ``confidence`` is the mean model word probability, not a correctness
    guarantee. Silence can return an empty list. The caller should let the user
    review recognition and timing before export.
    """
    _check_cancel(cancel)
    source = Path(str(project.get("source", ""))).expanduser()
    if not source.is_file():
        raise ValueError("Die Quelldatei für die Transkription fehlt.")
    source = source.resolve()
    info = _probe_source(source)
    if not info.get("has_audio"):
        raise RuntimeError("Das ausgewählte Video hat keine Tonspur.")
    duration = float(info["duration"])
    ranges: list[dict] = []
    for part in project.get("segments", []):
        try:
            start, end = float(part["start"]), float(part["end"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Ungültiger Zeitbereich für die Transkription.") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start or end > duration + 0.05:
            raise ValueError("Transkriptionsbereiche müssen innerhalb des Quellvideos liegen und eine positive Länge haben.")
        ranges.append({"start": start, "end": min(end, duration)})
    if not ranges:
        raise ValueError("Mindestens einen Zeitbereich für die Transkription auswählen.")
    model_name = str(project.get("transcription_model") or "medium").strip()
    language = project.get("transcription_language") or None
    if language is not None:
        language = str(language).strip() or None
    _report(progress, "Prüfe Quelldatei und vorhandenes Transkript.", 0.01)
    fingerprint = _fingerprint(source, cancel)
    metadata = {"version": _CACHE_VERSION, "source": fingerprint, "model": model_name, "language": language, "segments": ranges}
    cache = _cache_path(metadata)
    cached = _read_cache(cache, metadata, ranges)
    if cached is not None:
        _check_cancel(cancel)
        _report(progress, "Vorhandenes Transkript geladen. Untertitel vor dem Export prüfen.", 1.0)
        return cached
    model = _load_model(model_name, progress, cancel)
    pages: list[dict] = []
    total = sum(part["end"] - part["start"] for part in ranges)
    completed = 0.0
    with tempfile.TemporaryDirectory(prefix="cng-transcribe-") as temporary:
        for index, part in enumerate(ranges):
            _check_cancel(cancel)
            start, end = part["start"], part["end"]
            segment_duration = end - start
            _report(progress, f"Tonspur für Ausschnitt {index+1}/{len(ranges)} vorbereiten.", 0.08 + 0.88 * completed / total)
            wav = Path(temporary) / f"segment-{index:04d}.wav"
            _extract_audio(source, start, end, wav, cancel)
            _report(progress, f"Erkenne Sprache in Ausschnitt {index+1}/{len(ranges)}. CPU-Verarbeitung kann dauern.", 0.08 + 0.88 * completed / total)
            _check_cancel(cancel)
            try:
                recognized, _ = model.transcribe(str(wav), language=language, task="transcribe", beam_size=5,
                    word_timestamps=True, vad_filter=True, condition_on_previous_text=False,
                    hallucination_silence_threshold=2.0)
                words: list[dict] = []
                for segment in recognized:
                    _check_cancel(cancel)
                    words.extend(_segment_words(segment, segment_duration))
                    current_end = min(segment_duration, max(0.0, float(segment.end)))
                    _report(progress, f"Erkenne Sprache in Ausschnitt {index+1}/{len(ranges)}.", 0.08 + 0.88 * (completed + current_end) / total)
                words.sort(key=lambda word: (word["start"], word["end"]))
                pages.extend(_make_pages(words, start, end))
            except TranscriptionCancelled:
                raise
            except Exception as exc:
                raise RuntimeError(f"Spracherkennung für Ausschnitt {index+1} fehlgeschlagen: {exc}") from exc
            completed += segment_duration
    _check_cancel(cancel)
    # Do not cache speech from a source being overwritten by another program.
    current_stat = source.stat()
    if (current_stat.st_size, current_stat.st_mtime_ns) != (fingerprint["size"], fingerprint["mtime_ns"]):
        raise RuntimeError("Die Quelldatei wurde während der Transkription geändert. Ergebnis wurde nicht gespeichert.")
    try:
        _write_cache(cache, metadata, pages, cancel)
    except OSError as exc:
        _report(progress, f"Transkript erstellt; Zwischenspeicher konnte nicht geschrieben werden: {exc}", 0.99)
    _report(progress, "Transkript erstellt. Erkannten Text und Zeitmarken vor dem Export prüfen." if pages else "Keine Sprache erkannt. Untertitel bei Bedarf manuell eintragen.", 1.0)
    return pages
