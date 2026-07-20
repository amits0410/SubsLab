import hashlib
import io
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from subsgen.domain import TranscriptionMode, TranscriptionRequest
from subsgen.model_store import ArtifactDownloader, ModelRoutingError, ModelStore, get_manifest, route_request


class RoutingTests(unittest.TestCase):
    def request(self, mode, language=None, model_id=None):
        return TranscriptionRequest(Path("media.wav"), mode, language, model_id=model_id)

    def test_hebrew_always_routes_to_ivrit(self):
        selected = route_request(self.request(TranscriptionMode.TRANSCRIBE, "he"), "windows", "amd64")
        self.assertEqual(selected.id, "ivrit-whisper-large-v3-turbo-ct2")

    def test_catalog_models_are_pinned_and_checksum_verified(self):
        for model_id in ("whisper-small-ct2", "ivrit-whisper-large-v3-turbo-ct2", "whisper-small-mlx"):
            manifest = get_manifest(model_id)
            self.assertRegex(manifest.revision, r"^[0-9a-f]{40}$")
            self.assertRegex(manifest.checksum or "", r"^[0-9a-f]{64}$")
        self.assertEqual(get_manifest("whisper-small-mlx").repository, "mlx-community/whisper-small-mlx")

    def test_string_mode_from_qt_is_normalized_before_routing(self):
        request = TranscriptionRequest(Path("media.wav"), "transcribe", "HE")
        self.assertIs(request.mode, TranscriptionMode.TRANSCRIBE)
        self.assertEqual(request.language, "he")
        selected = route_request(request, "windows", "amd64")
        self.assertEqual(selected.id, "ivrit-whisper-large-v3-turbo-ct2")

    def test_task_property_tolerates_mode_replaced_by_ipc_string(self):
        request = TranscriptionRequest(Path("media.wav"), TranscriptionMode.TRANSCRIBE, "he")
        request.mode = "transcribe"
        self.assertEqual(request.task, "transcribe")

    def test_hebrew_rejects_generic_override(self):
        with self.assertRaises(ModelRoutingError):
            route_request(self.request(TranscriptionMode.TRANSCRIBE, "he", "whisper-small-ct2"), "windows", "amd64")

    def test_translation_rejects_ivrit(self):
        with self.assertRaises(ModelRoutingError):
            route_request(self.request(TranscriptionMode.TRANSLATE, "he", "ivrit-whisper-large-v3-turbo-ct2"), "windows", "amd64")

    def test_apple_silicon_uses_mlx_for_general_model(self):
        selected = route_request(self.request(TranscriptionMode.TRANSCRIBE, "en"), "darwin", "arm64")
        self.assertEqual(selected.id, "whisper-small-mlx")


class RangeHandler(BaseHTTPRequestHandler):
    payload = b""

    def do_GET(self):
        offset = 0
        if self.headers.get("Range"):
            offset = int(self.headers["Range"].split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {offset}-{len(self.payload)-1}/{len(self.payload)}")
        else:
            self.send_response(200)
        body = self.payload[offset:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        RangeHandler.payload = b"offline-model-payload"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_resumes_and_verifies_download(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "model.bin"
            destination.with_suffix(".bin.part").write_bytes(RangeHandler.payload[:7])
            expected = hashlib.sha256(RangeHandler.payload).hexdigest()
            ArtifactDownloader().download(
                f"http://127.0.0.1:{self.server.server_port}/model",
                destination,
                expected,
                len(RangeHandler.payload),
            )
            self.assertEqual(destination.read_bytes(), RangeHandler.payload)
            self.assertFalse(destination.with_suffix(".bin.part").exists())

    def test_checksum_failure_never_replaces_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "model.bin"
            with self.assertRaises(IOError):
                ArtifactDownloader().download(
                    f"http://127.0.0.1:{self.server.server_port}/model",
                    destination,
                    "0" * 64,
                )
            self.assertFalse(destination.exists())


class ModelStoreTests(unittest.TestCase):
    def test_install_uses_atomic_partial_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ModelStore(Path(directory) / "models")
            manifest = replace(
                get_manifest("whisper-small-ct2"),
                checksum=hashlib.sha256(b"verified").hexdigest(),
            )
            reported = []

            def fake_snapshot_download(**kwargs):
                partial = Path(kwargs["local_dir"])
                progress = kwargs["tqdm_class"](total=10, desc="weights.bin", file=io.StringIO(), mininterval=0)
                progress.update(4)
                progress.update(6)
                progress.close()
                partial.mkdir(parents=True, exist_ok=True)
                for filename in manifest.required_files:
                    (partial / filename).write_bytes(b"verified")
                self.assertNotIn("local_dir_use_symlinks", kwargs)
                return str(partial)

            with (
                patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot_download),
                patch("subsgen.model_store.shutil.disk_usage", return_value=SimpleNamespace(free=10**12)),
            ):
                installed = store.install(manifest, download_progress=lambda current, total, name: reported.append((current, total, name)))
            self.assertEqual(installed, store.path_for(manifest))
            self.assertTrue(store.is_installed(manifest))
            store.verify(manifest)
            (installed / "model.bin").write_bytes(b"tampered model")
            self.assertFalse(store.is_installed(manifest))
            self.assertFalse((store.root / f".{manifest.id}.partial").exists())
            self.assertIn((4, 10, "weights.bin"), reported)
            self.assertIn((10, 10, "weights.bin"), reported)


if __name__ == "__main__":
    unittest.main()
