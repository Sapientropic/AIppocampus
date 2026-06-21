from __future__ import annotations

import unittest

from aippocampus_runtime.navigation import avatar_posture


class AvatarPostureTests(unittest.TestCase):
    def test_reducer_emits_stable_posture_ids(self) -> None:
        closeout = avatar_posture.reduce_avatar_posture(
            {
                "title": "release closeout",
                "task_family": "closeout",
                "source_refs": [{"source_id": "source:release"}],
            }
        )
        seed = avatar_posture.reduce_avatar_posture(
            {
                "title": "seed probe",
                "task_family": "seed",
                "source_refs": [{"source_id": "source:seed"}],
            }
        )

        self.assertEqual(closeout["posture_id"], "closeout")
        self.assertEqual(seed["posture_id"], "seed_probe")
        self.assertEqual(closeout["authority_level"], "direction_only")
        self.assertEqual(closeout["claim_permission"], "none")

    def test_thin_or_conflicting_posture_is_ambiguous(self) -> None:
        thin = avatar_posture.reduce_avatar_posture({"title": "closeout"})
        conflicting = avatar_posture.reduce_avatar_posture(
            {
                "title": "seed probe closeout",
                "source_refs": [{"source_id": "source:mixed"}],
            }
        )

        self.assertEqual(thin["posture_id"], "ambiguous_posture")
        self.assertEqual(conflicting["posture_id"], "ambiguous_posture")
        self.assertFalse(conflicting["foreground_eligible"])

    def test_posture_edge_is_direction_only_and_never_glue(self) -> None:
        edge = avatar_posture.posture_dependency_edge(
            {"section_id": "a", "posture_id": "closeout"},
            {"section_id": "b", "posture_id": "verifier"},
        )

        self.assertIsNotNone(edge)
        self.assertEqual(edge["edge_kind"], "posture_dependency_edge")
        self.assertFalse(edge["may_satisfy_glue"])
        self.assertFalse(edge["may_transfer_fact"])

if __name__ == "__main__":
    unittest.main()
