"""Reference import: hash, rights metadata, immutable workspace store."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID

from backend.app.audio.io import (
    SUPPORTED_EXTENSIONS,
    AudioLoadError,
    load_audio,
    wav_header_info,
)
from backend.app.core.config import Settings, get_settings
from backend.app.models.schemas import (
    BorrowTrait,
    LicenseClass,
    ReferenceAsset,
    UseMode,
    new_id,
    utcnow,
)
from backend.app.storage.assets import AssetStore

# Soft size ceiling (bytes) — configurable later
DEFAULT_MAX_BYTES = 200 * 1024 * 1024


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def import_reference(
    source: Path,
    *,
    settings: Settings | None = None,
    license_class: LicenseClass | str = LicenseClass.UNKNOWN,
    permission_notes: str | None = None,
    use_mode: UseMode | str = UseMode.ANALYSIS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    reference_id: UUID | None = None,
) -> ReferenceAsset:
    """Copy audio into immutable workspace store and return ReferenceAsset.

    The original bytes are stored under ``workspace/references/<id>/original.*``.
    Analysis WAV derivative is written under ``analysis.wav`` (non-destructive).
    """
    settings = settings or get_settings()
    assets = AssetStore(settings)
    source = Path(source).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise AudioLoadError(f"reference file not found: {source}")

    ext = source.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise AudioLoadError(
            f"unsupported format {ext}; accepted: {sorted(SUPPORTED_EXTENSIONS)}"
        )

    size = source.stat().st_size
    if size <= 0:
        raise AudioLoadError("empty audio file")
    if size > max_bytes:
        raise AudioLoadError(f"file too large ({size} bytes > {max_bytes})")

    digest = sha256_file(source)
    ref_id = reference_id or new_id()
    ref_dir = assets.reference_dir(ref_id)
    original_dest = ref_dir / f"original{ext}"
    if original_dest.exists():
        # Content-addressable: if same hash already there, reuse
        if sha256_file(original_dest) != digest:
            raise AudioLoadError("immutable original already exists with different hash")
    else:
        assets.copy_into(source, f"references/{ref_id}/original{ext}")

    # Verify immutable copy
    if sha256_file(original_dest) != digest:
        raise AudioLoadError("immutable store integrity check failed")

    analysis_wav = ref_dir / "analysis.wav"
    samples, sr, _ = load_audio(original_dest, target_sr=22050, analysis_wav_out=analysis_wav)
    duration = len(samples) / float(sr)
    channels = 1
    if ext == ".wav":
        try:
            info = wav_header_info(original_dest)
            channels = int(info["channels"])
        except Exception:  # noqa: BLE001
            channels = 1

    if isinstance(license_class, str):
        license_class = LicenseClass(license_class)
    if isinstance(use_mode, str):
        use_mode = UseMode(use_mode)

    asset = ReferenceAsset(
        id=ref_id,
        original_filename=source.name,
        immutable_sha256=digest,
        source_uri_or_local_path=str(original_dest),
        license_class=license_class,
        permission_notes=permission_notes,
        use_mode=use_mode,
        imported_at=utcnow(),
        duration_sec=duration,
        sample_rate=sr,
        channels=channels,
        analysis_status="pending",
        analysis_wav_path=str(analysis_wav),
        available_borrow_traits=[t.value for t in BorrowTrait],
        lineage={
            "import": {
                "source_path": str(source),
                "bytes": size,
                "sha256": digest,
                "pipeline": "phase2-ingest-v1",
            }
        },
    )

    # Persist metadata JSON next to blobs
    meta_path = ref_dir / "reference.json"
    meta_path.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
    # Hash index for duplicate detection
    index_path = assets.root / "references" / "by_hash" / f"{digest}.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        index_path.write_text(
            json.dumps({"reference_id": str(ref_id), "sha256": digest}, indent=2),
            encoding="utf-8",
        )
    return asset


def find_reference_by_hash(digest: str, settings: Settings | None = None) -> UUID | None:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    index_path = assets.root / "references" / "by_hash" / f"{digest}.json"
    if not index_path.exists():
        return None
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return UUID(data["reference_id"])


def load_reference_asset(reference_id: UUID, settings: Settings | None = None) -> ReferenceAsset:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    meta = assets.reference_dir(reference_id) / "reference.json"
    if not meta.exists():
        raise FileNotFoundError(f"reference metadata missing: {reference_id}")
    return ReferenceAsset.model_validate_json(meta.read_text(encoding="utf-8"))


def save_reference_asset(asset: ReferenceAsset, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    assets = AssetStore(settings)
    meta = assets.reference_dir(asset.id) / "reference.json"
    meta.write_text(asset.model_dump_json(indent=2), encoding="utf-8")
    return meta
