from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "aippocampus" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aippocampus_runtime.macro import hexagram  # noqa: E402


class MacroHexagramTests(unittest.TestCase):
    def test_bit_order_and_trigrams_are_bottom_to_top(self) -> None:
        tun = hexagram.hexagram_by_name("屯")
        jiji = hexagram.hexagram_by_name("既济")

        self.assertEqual(tun.lines, (1, 0, 0, 0, 1, 0))
        self.assertEqual(tun.bitstring_bottom_to_top, "100010")
        self.assertEqual(tun.lower_trigram, "震")
        self.assertEqual(tun.upper_trigram, "坎")
        self.assertEqual(hexagram.hexagram_from_lines((1, 0, 0, 0, 1, 0)).name, "屯")

        self.assertEqual(jiji.lines, (1, 0, 1, 0, 1, 0))
        self.assertEqual(jiji.lower_trigram, "离")
        self.assertEqual(jiji.upper_trigram, "坎")

    def test_structural_transforms_match_research_anchors(self) -> None:
        anchors = {
            "屯": {"nuclear": "剥", "opposite": "鼎", "reverse": "蒙"},
            "革": {"nuclear": "姤", "opposite": "蒙", "reverse": "鼎"},
            "谦": {"nuclear": "解", "opposite": "履", "reverse": "豫"},
            "既济": {"nuclear": "未济", "opposite": "未济", "reverse": "未济"},
        }

        for name, expected in anchors.items():
            with self.subTest(name=name):
                item = hexagram.hexagram_by_name(name)
                self.assertEqual(item.nuclear.name, expected["nuclear"])
                self.assertEqual(item.opposite.name, expected["opposite"])
                self.assertEqual(item.reverse.name, expected["reverse"])

    def test_changing_lines_are_one_based_and_bottom_to_top(self) -> None:
        self.assertEqual(hexagram.change_lines("屯", (1, 2, 5, 6)).name, "蒙")
        self.assertEqual(hexagram.changed_lines("屯", "蒙"), (1, 2, 5, 6))
        self.assertEqual(hexagram.hexagram_by_name("乾").change_lines((1,)).name, "姤")

    def test_king_wen_adjacency_is_sequence_only(self) -> None:
        tun = hexagram.hexagram_by_name("屯")

        self.assertEqual(tun.wen_prev.name if tun.wen_prev else None, "坤")
        self.assertEqual(tun.wen_next.name if tun.wen_next else None, "蒙")
        self.assertIsNone(hexagram.hexagram_by_name("乾").wen_prev)
        self.assertIsNone(hexagram.hexagram_by_name("未济").wen_next)

    def test_six_bit_gray_walk_covers_all_states_with_single_line_steps(self) -> None:
        sequence = hexagram.SIX_BIT_GRAY_WALK_SEQUENCE

        self.assertEqual(len(sequence), 64)
        self.assertEqual({item.lines for item in sequence}, {item.lines for item in hexagram.HEXAGRAMS})
        for index, (left, right) in enumerate(zip(sequence, sequence[1:], strict=False)):
            with self.subTest(index=index):
                self.assertEqual(hexagram.hamming_distance(left, right), 1)
        self.assertEqual(hexagram.gray_walk_index(sequence[0]), 0)
        self.assertEqual(hexagram.hexagram_by_gray_walk_index(0).lines, sequence[0].lines)
        self.assertIsNone(hexagram.gray_walk_prev(sequence[0]))
        self.assertIsNone(hexagram.gray_walk_next(sequence[-1]))
        self.assertEqual(
            hexagram.hamming_distance(
                hexagram.gray_walk_prev(sequence[0], wrap=True),
                sequence[0],
            ),
            1,
        )

    def test_king_wen_pair_relation_classifies_all_adjacent_pairs(self) -> None:
        inventory = hexagram.king_wen_pair_relation_inventory()
        qian = hexagram.king_wen_pair_relation("乾")
        ji = hexagram.king_wen_pair_relation("既济")

        self.assertEqual(inventory["pair_count"], 32)
        self.assertEqual(inventory["relation_counts"]["reverse"], 24)
        self.assertEqual(inventory["relation_counts"]["opposite"], 4)
        self.assertEqual(inventory["relation_counts"]["reverse_and_opposite"], 4)
        self.assertEqual(qian["pair_mate"]["name"], "坤")
        self.assertEqual(qian["relation"], "opposite")
        self.assertEqual(ji["pair_mate"]["name"], "未济")
        self.assertEqual(ji["relation"], "reverse_and_opposite")
        self.assertEqual(qian["authority_level"], "navigation_only")
        self.assertFalse(qian["fact_claim_allowed"])

    def test_hamming_helpers_report_exact_structure_not_advice(self) -> None:
        self.assertEqual(hexagram.hamming_distance("屯", "蒙"), 4)
        self.assertEqual(hexagram.changed_lines("屯", "蒙"), (1, 2, 5, 6))

        self.assertEqual(hexagram.perturbation_band(0), "none")
        self.assertEqual(hexagram.perturbation_band(1), "local")
        self.assertEqual(hexagram.perturbation_band(2), "local")
        self.assertEqual(hexagram.perturbation_band(3), "medium")
        self.assertEqual(hexagram.perturbation_band(4), "large")
        self.assertEqual(hexagram.perturbation_band(5), "large")
        self.assertEqual(hexagram.perturbation_band(6), "inversion")

    def test_public_projection_is_structure_only(self) -> None:
        projection = hexagram.public_hexagram_projection("屯")
        encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True)

        self.assertEqual(projection["runtime_boundary"]["deterministic_structure_only"], True)
        self.assertFalse(projection["runtime_boundary"]["interpretation_included"])
        self.assertFalse(projection["runtime_boundary"]["model_calls"])
        self.assertNotIn("爻辞", encoded)
        self.assertNotIn("commentary", encoded)
        self.assertNotIn("interpretation_text", encoded)

    def test_invalid_or_ambiguous_inputs_are_rejected(self) -> None:
        for bad_name in ("不存在", " 屯", "屯 "):
            with self.subTest(bad_name=bad_name):
                with self.assertRaises(ValueError):
                    hexagram.hexagram_by_name(bad_name)

        for bad_positions in ((0,), (7,), (1, 1), (True,)):
            with self.subTest(bad_positions=bad_positions):
                with self.assertRaises(ValueError):
                    hexagram.change_lines("屯", bad_positions)

        with self.assertRaises(ValueError):
            hexagram.hexagram_from_lines((1, 0, 0))
        with self.assertRaises(ValueError):
            hexagram.perturbation_band(7)
        with self.assertRaises(ValueError):
            hexagram.trigram_from_lines((1, 2, 0))

    def test_runtime_does_not_import_research_prototype(self) -> None:
        module_path = Path(hexagram.__file__).resolve()

        self.assertNotIn("docs", module_path.parts)
        self.assertEqual(len(hexagram.HEXAGRAMS), 64)
        self.assertEqual(len(hexagram.HEXAGRAMS_BY_NAME), 64)
        self.assertEqual(len(hexagram.HEXAGRAMS_BY_LINES), 64)


if __name__ == "__main__":
    unittest.main()
