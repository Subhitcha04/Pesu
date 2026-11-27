"""Audio upload handling (A6).

v0.1 bugs: only 'ogg' was recognised (Safari/iOS records audio/mp4 but it was stored as .webm
and served with the wrong MIME), any bytes up to 2 MB were accepted as "audio", and the whole
upload was read into memory before the size check.

Now: read in 64 KB chunks with a hard cap (413), sniff the magic bytes (415 for anything that
isn't WebM, Ogg, MP4/M4A or WAV), and take the extension + MIME from the sniffed type,
never from the client's Content-Type.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import settings

CHUNK = 64 * 1024

# name: (extension, media type)
TYPES = {
    "webm": (".webm", "audio/webm"),
    "ogg": (".ogg", "audio/ogg"),
    "mp4": (".m4a", "audio/mp4"),
    "wav": (".wav", "audio/wav"),
}


def sniff(head: bytes) -> str | None:
    """Identify an audio container from its first bytes."""
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"  # EBML header (WebM / Matroska)
    if head[:4] == b"OggS":
        return "ogg"
    if head[4:8] == b"ftyp":
        return "mp4"  # ISO base media: ....ftypM4A / isom / mp42
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    return None


async def read_capped(upload: UploadFile, cap: int | None = None) -> bytes:
    cap = cap or settings.max_audio_bytes
    data = bytearray()
    while True:
        chunk = await upload.read(CHUNK)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > cap:
            raise HTTPException(413, f"Audio larger than {cap} bytes")
    return bytes(data)


async def save_audio(upload: UploadFile, folder: Path, stem: str) -> tuple[str, str]:
    """Validate and store an upload. Returns (path relative to data dir, media type)."""
    data = await read_capped(upload)
    kind = sniff(data[:16])
    if kind is None:
        raise HTTPException(415, "Not a supported audio file (WebM, Ogg, MP4/M4A or WAV)")
    ext, mime = TYPES[kind]
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{stem}.*"):  # re-recording may change the container type
        old.unlink()
    path = folder / f"{stem}{ext}"
    path.write_bytes(data)
    return str(path.relative_to(settings.data_dir)), mime


def safe_path(rel: str) -> Path:
    """Resolve a stored relative path and refuse anything outside the data dir (path traversal)."""
    path = (settings.data_dir / rel).resolve()
    if settings.data_dir.resolve() not in path.parents:
        raise HTTPException(404, "Not found")
    return path
