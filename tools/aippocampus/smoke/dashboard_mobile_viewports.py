#!/usr/bin/env python3
"""Capture the vault dashboard at the mobile/narrow/desktop QA viewports."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "skills" / "aippocampus" / "scripts"))

from aippocampus_runtime.vault.dashboard import html_dashboard_v2  # noqa: E402

VIEWPORTS = ("390,844", "760,844", "1278,900")


def _sample_dashboard(output_dir: Path) -> Path:
    html_path = output_dir / "dashboard-mobile-smoke.html"
    html_path.write_text(
        html_dashboard_v2(
            thread_name="Dashboard mobile smoke",
            health={
                "ok": False,
                "status": "attention_needed",
                "product_readiness": {
                    "ordinary_first_recall_usable": False,
                    "freshness_degraded": True,
                    "blocks_exact_latest_claims": True,
                },
                "recommended_actions": [
                    {
                        "id": "build_clean_source",
                        "severity": "critical",
                        "command": "aippocampus maintenance --cwd . --json",
                    }
                ],
                "anchors": {"count": 3},
                "rollout": {"message_count": 18},
            },
            anchors=[
                {
                    "title": f"Long navigation anchor {idx}",
                    "message": "sample route context " * 18,
                    "score": 0.82,
                }
                for idx in range(1, 18)
            ],
            checkpoint_state={"latest": "checkpoint smoke"},
            recent_messages=[
                {"role": "user", "content": "continue dashboard mobile scroll issue"},
                {"role": "assistant", "content": "Foreground action card and viewport smoke."},
            ]
            * 8,
            vault=ROOT,
            assets={},
        ),
        encoding="utf-8",
    )
    return html_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / ".tmp" / "dashboard-mobile-viewports"),
        help="Directory for temporary HTML and screenshots.",
    )
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = _sample_dashboard(output_dir)
    npx = shutil.which("npx")
    if not npx:
        print(json.dumps({"ok": False, "error": "npx_not_found"}, ensure_ascii=False))
        return 2
    url = html_path.as_uri()
    shots: list[dict[str, str]] = []
    for viewport in VIEWPORTS:
        shot = output_dir / f"dashboard-{viewport.replace(',', 'x')}.png"
        subprocess.run(
            [
                npx,
                "--yes",
                "playwright",
                "screenshot",
                "--viewport-size",
                viewport,
                "--wait-for-selector",
                ".foreground-action-card",
                "--wait-for-timeout",
                "500",
                url,
                str(shot),
            ],
            check=True,
            cwd=ROOT,
        )
        shots.append({"viewport": viewport, "screenshot": str(shot)})
    print(
        json.dumps(
            {"ok": True, "html": str(html_path), "screenshots": shots},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
