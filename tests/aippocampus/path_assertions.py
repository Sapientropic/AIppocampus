from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence
from unittest import TestCase


def assert_same_path(testcase: TestCase, actual: Path | str, expected: Path | str) -> None:
    testcase.assertEqual(Path(actual).resolve(), Path(expected).resolve())


def assert_path_flag_points_to(
    testcase: TestCase,
    argv: Sequence[str],
    flag: str,
    expected_path: Path | str,
) -> None:
    testcase.assertIn(flag, argv)
    index = argv.index(flag)
    testcase.assertLess(index + 1, len(argv), f"{flag} missing path value")
    assert_same_path(testcase, argv[index + 1], expected_path)


def assert_path_list_contains(
    testcase: TestCase,
    path_list: str,
    expected_path: Path | str,
) -> None:
    expected = Path(expected_path).resolve()
    actual = [Path(item).resolve() for item in path_list.split(os.pathsep) if item]
    testcase.assertIn(expected, actual)
