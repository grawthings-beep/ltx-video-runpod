import hashlib
import importlib.util
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "download_models.py"
SPEC = importlib.util.spec_from_file_location("download_models", SCRIPT)
download_models = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download_models)


class DownloadModelsTest(unittest.TestCase):
    def test_parse_huggingface_resolve_url(self):
        parsed = download_models.parse_huggingface_url(
            "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/"
            "split_files/text_encoders/model.safetensors?download=true"
        )

        self.assertEqual(
            parsed,
            (
                "Comfy-Org/ltx-2",
                "main",
                "split_files/text_encoders/model.safetensors",
            ),
        )

    def test_hf_hub_download_moves_nested_file_to_requested_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "model.safetensors"

            def fake_download(**kwargs):
                self.assertEqual(kwargs["repo_id"], "org/repo")
                self.assertEqual(kwargs["revision"], "main")
                self.assertEqual(kwargs["filename"], "nested/model.safetensors")
                nested = pathlib.Path(kwargs["local_dir"]) / kwargs["filename"]
                nested.parent.mkdir(parents=True)
                nested.write_bytes(b"xet data")
                return str(nested)

            fake_module = types.SimpleNamespace(hf_hub_download=fake_download)
            with mock.patch.dict(sys.modules, {"huggingface_hub": fake_module}):
                download_models.run_hf_hub(
                    "https://huggingface.co/org/repo/resolve/main/nested/model.safetensors",
                    output,
                    {"Authorization": "Bearer token"},
                )

            self.assertEqual(output.read_bytes(), b"xet data")

    def test_aria2_uses_partial_file_then_renames_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "model.safetensors"

            def fake_run(command, check):
                self.assertTrue(check)
                directory = pathlib.Path(command[command.index("-d") + 1])
                filename = command[command.index("-o") + 1]
                self.assertEqual(filename, "model.safetensors.part")
                self.assertFalse(output.exists())
                (directory / filename).write_bytes(b"complete")

            with mock.patch.object(download_models.subprocess, "run", side_effect=fake_run):
                download_models.run_aria2("https://example.invalid/model", output, 8, 8)

            self.assertEqual(output.read_bytes(), b"complete")
            self.assertFalse(download_models.partial_path(output).exists())

    def test_legacy_aria2_download_is_moved_to_partial_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "model.safetensors"
            legacy_control = pathlib.Path(str(output) + ".aria2")
            output.write_bytes(b"incomplete")
            legacy_control.write_bytes(b"aria state")

            download_models.migrate_legacy_aria_download(output)

            partial = download_models.partial_path(output)
            self.assertFalse(output.exists())
            self.assertEqual(partial.read_bytes(), b"incomplete")
            self.assertEqual(pathlib.Path(str(partial) + ".aria2").read_bytes(), b"aria state")

    def test_once_verification_uses_marker_on_later_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = pathlib.Path(temp_dir) / "model.safetensors"
            output.write_bytes(b"model data")
            expected = hashlib.sha256(b"model data").hexdigest().upper()

            self.assertTrue(download_models.verify_sha256(output, expected, "model", "once"))

            with mock.patch.object(
                download_models,
                "sha256_file",
                side_effect=AssertionError("file should not be rehashed"),
            ):
                self.assertTrue(download_models.verify_sha256(output, expected, "model", "once"))


if __name__ == "__main__":
    unittest.main()
