from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import urllib.request
from pathlib import Path
from typing import Callable

from .domain import BackendKind, ModelManifest, TranscriptionMode, TranscriptionRequest

DownloadProgress = Callable[[int, int | None], None]
ModelDownloadProgress = Callable[[int, int | None, str], None]


MODEL_CATALOG: tuple[ModelManifest, ...] = (
    ModelManifest(
        id="whisper-small-ct2",
        display_name="Whisper Small (multilingual)",
        repository="Systran/faster-whisper-small",
        backend=BackendKind.FASTER_WHISPER,
        languages=("*",),
        tasks=(TranscriptionMode.TRANSCRIBE, TranscriptionMode.TRANSLATE),
        approximate_size=1_000_000_000,
        platforms=("windows", "darwin"),
        hardware=("cpu", "cuda"),
        revision="536b0662742c02347bc0e980a01041f333bce120",
        checksum="3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
        required_files=("config.json", "model.bin"),
    ),
    ModelManifest(
        id="ivrit-whisper-large-v3-turbo-ct2",
        display_name="Ivrit-AI Hebrew Large v3 Turbo",
        repository="ivrit-ai/whisper-large-v3-turbo-ct2",
        backend=BackendKind.FASTER_WHISPER,
        languages=("he",),
        tasks=(TranscriptionMode.TRANSCRIBE,),
        approximate_size=1_700_000_000,
        platforms=("windows", "darwin"),
        hardware=("cpu", "cuda"),
        revision="72ad623a37947395efcc3933132353790e5a12f5",
        checksum="db2a2265aa012c16c7db9edda3d699c99f984efdd3f2e22a72a8ce7e9720f3a2",
        required_files=("config.json", "model.bin"),
    ),
    ModelManifest(
        id="whisper-small-mlx",
        display_name="Whisper Small (Apple Silicon)",
        repository="mlx-community/whisper-small-mlx",
        backend=BackendKind.MLX_WHISPER,
        languages=("*",),
        tasks=(TranscriptionMode.TRANSCRIBE, TranscriptionMode.TRANSLATE),
        approximate_size=1_000_000_000,
        platforms=("darwin",),
        hardware=("apple-silicon",),
        revision="45f3915923c7a79a5a5b5a7d909d39aeb0e5630e",
        checksum="55b6674c9b339702d486e2b1573839a66f8ec8f821ed2886993ef717a86b09f5",
        required_files=("config.json", "weights.npz"),
    ),
)


class ModelRoutingError(ValueError):
    pass


def current_platform() -> str:
    return platform.system().lower()


def available_models(system: str | None = None) -> list[ModelManifest]:
    system = (system or current_platform()).lower()
    return [manifest for manifest in MODEL_CATALOG if system in manifest.platforms]


def get_manifest(model_id: str) -> ModelManifest:
    for manifest in MODEL_CATALOG:
        if manifest.id == model_id:
            return manifest
    raise ModelRoutingError(f"Unknown model: {model_id}")


def route_request(request: TranscriptionRequest, system: str | None = None, machine: str | None = None) -> ModelManifest:
    system = (system or current_platform()).lower()
    machine = (machine or platform.machine()).lower()
    language = request.language.lower() if request.language else None

    if request.mode is TranscriptionMode.TRANSCRIBE and language == "he":
        required = get_manifest("ivrit-whisper-large-v3-turbo-ct2")
        if request.model_id and request.model_id != required.id:
            raise ModelRoutingError("Hebrew transcription requires the Ivrit-AI model")
        return required

    if request.model_id:
        selected = get_manifest(request.model_id)
        if system not in selected.platforms or not selected.supports(request.mode, language):
            raise ModelRoutingError("The selected model does not support this platform, language, or task")
        if request.mode is TranscriptionMode.TRANSLATE and selected.id.startswith("ivrit-"):
            raise ModelRoutingError("Ivrit-AI is transcription-only and cannot be used for translation")
        return selected

    if system == "darwin" and machine in {"arm64", "aarch64"}:
        return get_manifest("whisper-small-mlx")
    return get_manifest("whisper-small-ct2")


class ArtifactDownloader:
    """Resumable, verified single-file downloader used by tests and future manifests."""

    def download(
        self,
        url: str,
        destination: Path,
        expected_sha256: str,
        expected_size: int | None = None,
        progress: DownloadProgress | None = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".part")
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        with urllib.request.urlopen(request) as response:
            if offset and getattr(response, "status", 200) != 206:
                offset = 0
                partial.unlink(missing_ok=True)
            mode = "ab" if offset else "wb"
            total_header = response.headers.get("Content-Length")
            total = offset + int(total_header) if total_header else expected_size
            with partial.open(mode) as handle:
                downloaded = offset
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
        if expected_size is not None and partial.stat().st_size != expected_size:
            raise IOError("Downloaded file size does not match the manifest")
        if _sha256_file(partial) != expected_sha256.lower():
            raise IOError("Downloaded file checksum does not match the manifest")
        os.replace(partial, destination)


class ModelStore:
    METADATA_FILE = ".subsgen-model.json"

    def __init__(self, root: Path):
        self.root = root

    def path_for(self, manifest: ModelManifest) -> Path:
        return self.root / manifest.id

    def is_installed(self, manifest: ModelManifest) -> bool:
        directory = self.path_for(manifest)
        if not self.has_model_files(manifest):
            return False
        try:
            metadata = json.loads((directory / self.METADATA_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        try:
            weight = self._weight_file(manifest, directory)
            weight_matches = metadata.get("weight_file") == weight.name and metadata.get("weight_size") == weight.stat().st_size
        except OSError:
            return False
        return (
            metadata.get("repository") == manifest.repository
            and metadata.get("revision") == manifest.revision
            and metadata.get("checksum") == manifest.checksum
            and weight_matches
        )

    def has_model_files(self, manifest: ModelManifest) -> bool:
        directory = self.path_for(manifest)
        return directory.is_dir() and all((directory / name).is_file() for name in manifest.required_files)

    def _write_metadata(self, manifest: ModelManifest, directory: Path) -> None:
        weight = self._weight_file(manifest, directory)
        (directory / self.METADATA_FILE).write_text(
            json.dumps(
                {
                    "repository": manifest.repository,
                    "revision": manifest.revision,
                    "checksum": manifest.checksum,
                    "weight_file": weight.name,
                    "weight_size": weight.stat().st_size,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _weight_file(manifest: ModelManifest, directory: Path) -> Path:
        for name in ("model.bin", "weights.npz", "model.safetensors"):
            candidate = directory / name
            if candidate.is_file():
                return candidate
        raise IOError("Model manifest does not identify a verifiable weight file")

    def verify(
        self,
        manifest: ModelManifest,
        directory: Path | None = None,
        progress: DownloadProgress | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        directory = directory or self.path_for(manifest)
        missing = [name for name in manifest.required_files if not (directory / name).is_file()]
        if missing:
            raise IOError(f"Model download is incomplete; missing: {', '.join(missing)}")
        if not manifest.checksum:
            raise IOError("Model manifest does not contain a SHA-256 checksum")
        actual = _sha256_file(self._weight_file(manifest, directory), progress, cancelled)
        if actual != manifest.checksum.lower():
            raise IOError("Downloaded model checksum does not match the pinned manifest")
        self._write_metadata(manifest, directory)

    def install(
        self,
        manifest: ModelManifest,
        progress: Callable[[str], None] | None = None,
        download_progress: ModelDownloadProgress | None = None,
    ) -> Path:
        if self.is_installed(manifest):
            return self.path_for(manifest)
        self.root.mkdir(parents=True, exist_ok=True)
        partial = self.root / f".{manifest.id}.partial"
        required_space = max(0, manifest.approximate_size - _directory_size(partial))
        if shutil.disk_usage(self.root).free < required_space:
            raise OSError(f"Not enough disk space; approximately {required_space / 1e9:.1f} GB is required")
        if progress:
            progress(f"Downloading {manifest.display_name}…")
        try:
            from huggingface_hub import snapshot_download
            from tqdm.auto import tqdm
        except ImportError as exc:
            raise RuntimeError("Install the 'huggingface-hub' dependency to download models") from exc

        class ReportingTqdm(tqdm):
            def update(self, amount=1):
                displayed = super().update(amount)
                if download_progress:
                    download_progress(int(self.n), int(self.total) if self.total is not None else None, str(self.desc or "Model file"))
                return displayed

            def close(self):
                if download_progress and self.total is not None:
                    download_progress(int(self.total), int(self.total), str(self.desc or "Model file"))
                return super().close()

        partial.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=manifest.repository,
            revision=manifest.revision,
            local_dir=partial,
            tqdm_class=ReportingTqdm,
        )
        if progress:
            progress("Verifying required model files…")
        self.verify(
            manifest,
            partial,
            (lambda current, total: download_progress(current, total, "SHA-256 verification"))
            if download_progress else None,
        )
        destination = self.path_for(manifest)
        if destination.exists():
            shutil.rmtree(destination)
        if progress:
            progress("Installing verified model atomically…")
        os.replace(partial, destination)
        if progress:
            progress(f"Installed {manifest.display_name}")
        return destination

    def remove(self, manifest: ModelManifest) -> None:
        directory = self.path_for(manifest).resolve()
        root = self.root.resolve()
        if root not in directory.parents:
            raise ValueError("Refusing to remove a model outside the model store")
        if directory.exists():
            shutil.rmtree(directory)


def _sha256_file(
    path: Path,
    progress: DownloadProgress | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    digest = hashlib.sha256()
    total = path.stat().st_size
    processed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            if cancelled and cancelled():
                raise InterruptedError("Model verification cancelled")
            digest.update(chunk)
            processed += len(chunk)
            if progress:
                progress(processed, total)
    return digest.hexdigest()


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
