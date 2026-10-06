from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

from repo_audit.reporting import code_span, markdown_table, markdown_text, write_bar_chart


class ReportingTests(unittest.TestCase):
    def test_markdown_table_escapes_pipes(self) -> None:
        value = markdown_table(("Value",), (("left|right",),))
        self.assertIn("left\\|right", value)

    def test_markdown_text_neutralizes_markup_in_data(self) -> None:
        self.assertEqual("\\_\\_init\\_\\_.py", markdown_text("__init__.py"))
        self.assertEqual("\\[x\\](y).py", markdown_text("[x](y).py"))
        self.assertEqual(
            "a\\*b\\* \\`c\\` \\<d\\> \\$e\\$ \\&f", markdown_text("a*b* `c` <d> $e$ &f")
        )
        self.assertEqual("one two", markdown_text("one\ntwo"))

    def test_code_span_uses_a_longer_fence_than_the_content(self) -> None:
        self.assertEqual("`main`", code_span("main"))
        self.assertEqual("``a`b``", code_span("a`b"))
        self.assertEqual("`` `edge` ``", code_span("`edge`"))

    def test_svg_chart_is_valid_xml_and_escapes_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chart.svg"
            write_bar_chart(path, "Example <&>", (("A & B", Decimal(10)), ("<C>", Decimal(5))))
            root = ET.parse(path).getroot()
            self.assertTrue(root.tag.endswith("svg"))
            texts = [element.text or "" for element in root.iter() if element.tag.endswith("text")]
            self.assertIn("Example <&>", texts)

    def test_svg_chart_handles_empty_and_zero_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "chart.svg"
            write_bar_chart(path, "Empty", ())
            ET.parse(path)
            write_bar_chart(path, "Zero", (("A", Decimal(0)),))
            ET.parse(path)


if __name__ == "__main__":
    unittest.main()
