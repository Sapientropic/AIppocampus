from __future__ import annotations

import unittest

from tests.aippocampus.product_probe_helpers import (
    SourceOpenExpectation,
    assert_deepen_opened_expected_source,
)


class ProductProbeHelperTests(unittest.TestCase):
    def test_source_open_probe_fails_when_deepen_opens_wrong_anchor(self) -> None:
        deepen = {
            "status": "ok",
            "result": {
                "source_refs": [
                    {
                        "thread_key": "session:wrong",
                        "message_id": "msg_wrong",
                    }
                ],
                "source_window": {
                    "messages": [
                        {
                            "text": "This opened source is unrelated to the expected anchor."
                        }
                    ]
                },
            },
        }

        with self.assertRaises(AssertionError):
            assert_deepen_opened_expected_source(
                self,
                deepen,
                SourceOpenExpectation(
                    thread_key="session:expected",
                    message_id="msg_expected",
                    window_terms=("expected anchor",),
                ),
            )


if __name__ == "__main__":
    unittest.main()
