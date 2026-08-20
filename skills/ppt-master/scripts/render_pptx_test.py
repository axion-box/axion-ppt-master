from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


def load_render_module():
    """Load the sibling CLI without requiring raster dependencies in unit tests."""

    script = Path(__file__).with_name("render_pptx.py")
    spec = importlib.util.spec_from_file_location("ppt_master_render_pptx", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    dependency_stubs = {"pymupdf": mock.MagicMock(), "PIL": mock.MagicMock()}
    with mock.patch.dict(sys.modules, dependency_stubs):
        spec.loader.exec_module(module)
    return module


class RasterContractTest(unittest.TestCase):
    """Keep the helper unable to own LibreOffice or accept PPTX input."""

    def setUp(self) -> None:
        self.module = load_render_module()

    def test_parser_requires_pdf_and_output_dir(self) -> None:
        args = self.module.parse_args(
            ["--pdf", "deck.pdf", "--output-dir", "rendered", "--json"]
        )

        self.assertEqual(args.pdf, "deck.pdf")
        self.assertEqual(args.output_dir, "rendered")
        self.assertTrue(args.json)

    def test_parser_rejects_legacy_pptx_position(self) -> None:
        with self.assertRaises(SystemExit):
            self.module.parse_args(["deck.pptx", "--output-dir", "rendered"])

    def test_module_has_no_converter_entrypoint(self) -> None:
        self.assertFalse(hasattr(self.module, "convert_to_pdf"))
        self.assertFalse(hasattr(self.module, "resolve_soffice"))


if __name__ == "__main__":
    unittest.main()
