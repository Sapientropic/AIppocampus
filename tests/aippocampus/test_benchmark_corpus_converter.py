from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from unittest import mock

from tests.aippocampus.import_path_helpers import import_repo_root_module

converter = import_repo_root_module("benchmark_corpus.convert_to_aippocampus")

class BenchmarkCorpusConverterTests(unittest.TestCase):
    def test_missing_datasets_dependency_has_targeted_message(self) -> None:
        missing = ModuleNotFoundError("No module named 'datasets'", name="datasets")

        with mock.patch.object(converter.importlib, "import_module", side_effect=missing):
            with self.assertRaises(converter.OptionalDatasetDependencyError) as caught:
                converter.load_huggingface_dataset_loader("wildchat")

        message = str(caught.exception)
        self.assertIn("Hugging Face streaming source 'wildchat'", message)
        self.assertIn("install `datasets`", message)
        self.assertIn("--source wildchat/sharechat", message)

    def test_cli_reports_missing_datasets_without_traceback(self) -> None:
        err = converter.OptionalDatasetDependencyError("sharechat")

        with tempfile.TemporaryDirectory() as tmp:
            stderr = io.StringIO()
            argv = [
                "convert_to_aippocampus.py",
                "--source",
                "sharechat",
                "--subset",
                "chatgpt",
                "--max-convs",
                "1",
                "--output",
                tmp,
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(converter, "convert_sharechat", side_effect=err),
                contextlib.redirect_stderr(stderr),
                self.assertRaises(SystemExit) as caught,
            ):
                converter.main()

        self.assertEqual(caught.exception.code, 2)
        output = stderr.getvalue()
        self.assertIn("Error:", output)
        self.assertIn("install `datasets`", output)
        self.assertNotIn("Traceback", output)

if __name__ == "__main__":
    unittest.main()
