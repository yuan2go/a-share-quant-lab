"""Stock-code mapping and chronological research embargo checks."""
import unittest
from datetime import date

from ashare_quant_lab.symbols import qlib_to_symbol, symbol_to_qlib
from ashare_quant_lab.first_study import StudyError, validate_study_config


class SymbolAndStudyTests(unittest.TestCase):
    def test_codes_are_canonical(self):
        self.assertEqual(qlib_to_symbol(symbol_to_qlib("600519.SH")), "600519.SH")

    def test_label_embargo_guard(self):
        config = {
            "train": ["2021-01-01", "2022-12-01"],
            "valid": ["2023-01-01", "2023-12-01"],
            "test": ["2024-01-01", "2024-11-01"],
            "horizon": 10, "min_cross_section": 5,
        }
        with self.assertRaisesRegex(StudyError, "embargo"):
            validate_study_config(config, [
                date(2022, 12, 2), date(2023, 1, 1),
                date(2023, 12, 2), date(2024, 1, 1),
                date(2024, 11, 2),
            ])


if __name__ == "__main__":
    unittest.main()
