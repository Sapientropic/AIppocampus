#!/usr/bin/env python3
"""Scan release-facing files for accidental private paths and credentials.

This guard is intentionally narrower than a full secret-scanning product. It
checks the public surfaces that are easy to publish by accident, plus optional
release artifacts, and keeps noisy redaction-test fixture zones out of the
default gate. Maintainers can add one-off `--private-needle` values locally
without committing personal strings into the repository.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, cast

DEFAULT_EXCLUDED_PREFIXES = (
    "tests/",
    "benchmark_corpus/",
    "benchmarks/",
)
DEFAULT_EXCLUDED_NAMES = (
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.ico",
    "*.pdf",
    "*.sqlite",
    "*.db",
)
ALLOWLIST_MARKERS = (
    "FAKE_TEST",
    "<repo>",
    "<path>",
    "<token>",
    "<api-key>",
    "<secret>",
    "C:\\path",
    "C:/path",
    "C:\\Users\\<you>",
    "C:/Users/<you>",
    "/path/to/",
    "/private/var",
    "source://private/",
)


@dataclass(frozen=True)
class Finding:
    source: str
    path: str
    line: int
    check_id: str
    message: str
    match_preview: str


@dataclass(frozen=True)
class PatternCheck:
    check_id: str
    message: str
    pattern: re.Pattern[str]


PATTERN_CHECKS = (
    PatternCheck(
        "private_key_block",
        "private key block marker is present",
        re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    ),
    PatternCheck(
        "github_token",
        "GitHub token-shaped string is present",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    ),
    PatternCheck(
        "openai_token",
        "OpenAI token-shaped string is present",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    PatternCheck(
        "anthropic_token",
        "Anthropic token-shaped string is present",
        re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    ),
    PatternCheck(
        "authorization_bearer",
        "Authorization bearer token-shaped string is present",
        re.compile(r"\bAuthorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    ),
    PatternCheck(
        "credential_url",
        "credential-bearing URL is present",
        re.compile(r"\bhttps?://[^/\s:@]+:[^/\s:@]+@"),
    ),
    PatternCheck(
        "windows_local_path",
        "Windows absolute local path is present",
        re.compile(r"(?<![\w])(?:[A-Za-z]:[/\\](?:Users|Documents and Settings|private|SDY|CodexHome)[^ \t\r\n`'\")<>{}]*)"),
    ),
    PatternCheck(
        "posix_home_path",
        "POSIX home/private local path is present",
        re.compile(r"(?<![\w])/(?:Users|home|private)/[A-Za-z0-9._ -]+(?:/[^ \t\r\n`'\")<>{}]*)?"),
    ),
)


def repo_root_from(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    return current


def git_tracked_files(repo: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return sorted(path for path in repo.rglob("*") if path.is_file())
    return [repo / line for line in completed.stdout.splitlines() if line.strip()]


def relative_posix(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_default_excluded(relative: str) -> bool:
    if any(relative.startswith(prefix) for prefix in DEFAULT_EXCLUDED_PREFIXES):
        return True
    return any(fnmatch.fnmatch(relative, pattern) for pattern in DEFAULT_EXCLUDED_NAMES)


def read_text_file(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def redacted_preview(value: str, *, check_id: str) -> str:
    if check_id == "private_needle":
        return f"<private-needle:{len(value)} chars>"
    if len(value) <= 12:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def line_is_allowlisted(line: str) -> bool:
    return any(marker in line for marker in ALLOWLIST_MARKERS)


def scan_text(
    text: str,
    *,
    source: str,
    path: str,
    private_needles: Iterable[str] = (),
) -> list[Finding]:
    findings: list[Finding] = []
    needles = [needle for needle in private_needles if needle]
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line_is_allowlisted(line):
            continue
        for needle in needles:
            if needle in line:
                findings.append(
                    Finding(
                        source=source,
                        path=path,
                        line=line_number,
                        check_id="private_needle",
                        message="operator-supplied private string is present",
                        match_preview=redacted_preview(needle, check_id="private_needle"),
                    )
                )
        for check in PATTERN_CHECKS:
            for match in check.pattern.finditer(line):
                findings.append(
                    Finding(
                        source=source,
                        path=path,
                        line=line_number,
                        check_id=check.check_id,
                        message=check.message,
                        match_preview=redacted_preview(match.group(0), check_id=check.check_id),
                    )
                )
    return findings


def scan_paths(
    repo: Path,
    *,
    paths: Iterable[Path],
    private_needles: Iterable[str] = (),
    include_default_excluded: bool = False,
) -> tuple[int, list[Finding]]:
    findings: list[Finding] = []
    scanned = 0
    for path in paths:
        relative = relative_posix(repo, path)
        if not include_default_excluded and is_default_excluded(relative):
            continue
        text = read_text_file(path)
        if text is None:
            continue
        scanned += 1
        findings.extend(
            scan_text(
                text,
                source="tracked",
                path=relative,
                private_needles=private_needles,
            )
        )
    return scanned, findings


def _iter_zip_texts(archive: Path) -> Iterable[tuple[str, str]]:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            data = zf.read(info)
            if b"\x00" in data:
                continue
            try:
                yield info.filename, data.decode("utf-8")
            except UnicodeDecodeError:
                continue


def _iter_tar_texts(archive: Path) -> Iterable[tuple[str, str]]:
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            file_obj = tf.extractfile(member)
            if file_obj is None:
                continue
            data = file_obj.read()
            if b"\x00" in data:
                continue
            try:
                yield member.name, data.decode("utf-8")
            except UnicodeDecodeError:
                continue


def scan_artifacts(
    *,
    artifact_paths: Iterable[Path],
    private_needles: Iterable[str] = (),
) -> tuple[int, list[Finding]]:
    findings: list[Finding] = []
    scanned = 0
    for archive in artifact_paths:
        if not archive.exists():
            continue
        suffixes = "".join(archive.suffixes)
        if archive.suffix in {".whl", ".zip"}:
            iterator = _iter_zip_texts(archive)
        elif suffixes.endswith(".tar.gz") or archive.suffix in {".tgz", ".tar"}:
            iterator = _iter_tar_texts(archive)
        else:
            text = read_text_file(archive)
            if text is None:
                continue
            scanned += 1
            findings.extend(
                scan_text(
                    text,
                    source="artifact",
                    path=archive.name,
                    private_needles=private_needles,
                )
            )
            continue
        for member_name, text in iterator:
            scanned += 1
            findings.extend(
                scan_text(
                    text,
                    source="artifact",
                    path=f"{archive.name}!{member_name}",
                    private_needles=private_needles,
                )
            )
    return scanned, findings


def artifact_files(paths: Iterable[Path]) -> list[Path]:
    archives: list[Path] = []
    for path in paths:
        if path.is_dir():
            archives.extend(sorted(child for child in path.rglob("*") if child.is_file()))
        else:
            archives.append(path)
    return archives


def build_report(
    repo: Path,
    *,
    paths: Iterable[Path] | None = None,
    dist_paths: Iterable[Path] = (),
    private_needles: Iterable[str] = (),
    include_default_excluded: bool = False,
    max_findings: int = 200,
) -> dict[str, object]:
    tracked_paths = list(paths) if paths is not None else git_tracked_files(repo)
    scanned_files, findings = scan_paths(
        repo,
        paths=tracked_paths,
        private_needles=private_needles,
        include_default_excluded=include_default_excluded,
    )
    scanned_artifact_files, artifact_findings = scan_artifacts(
        artifact_paths=artifact_files(dist_paths),
        private_needles=private_needles,
    )
    findings.extend(artifact_findings)
    findings.sort(key=lambda finding: (finding.source, finding.path, finding.line, finding.check_id))
    total_findings = len(findings)
    safe_max_findings = max(0, int(max_findings))
    returned_findings = findings[:safe_max_findings] if safe_max_findings else []
    return {
        "kind": "aippocampus_public_boundary_report",
        "schema_version": 1,
        "ok": not findings,
        "scanned_files": scanned_files,
        "scanned_artifact_files": scanned_artifact_files,
        "finding_count": total_findings,
        "findings_returned": len(returned_findings),
        "findings_truncated": len(returned_findings) < total_findings,
        "max_findings": safe_max_findings,
        "findings": [asdict(finding) for finding in returned_findings],
        "default_excluded_prefixes": list(DEFAULT_EXCLUDED_PREFIXES),
        "notes": [
            "Default scan excludes noisy redaction-test fixture zones; use --include-default-excluded for audits.",
            "Use --private-needle locally for machine/user-specific strings; do not commit those strings.",
            "finding_count is the total count; findings is capped by --max-findings for agent-readable output.",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Scan an explicit path instead of all tracked files. Repeat for multiple paths.",
    )
    parser.add_argument(
        "--dist",
        action="append",
        default=[],
        help="Scan release artifacts or artifact directories such as dist/.",
    )
    parser.add_argument(
        "--private-needle",
        action="append",
        default=[],
        help="Private string to search for locally without committing it into this script.",
    )
    parser.add_argument(
        "--include-default-excluded",
        action="store_true",
        help="Include tests, benchmarks, benchmark_corpus, and binary-like tracked paths.",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=200,
        help="Maximum finding samples to include in output; finding_count still reports the total.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = repo_root_from(args.repo)
    paths = [repo / path for path in args.path] if args.path else None
    dist_paths = [repo / path for path in args.dist]
    report = build_report(
        repo,
        paths=paths,
        dist_paths=dist_paths,
        private_needles=args.private_needle,
        include_default_excluded=args.include_default_excluded,
        max_findings=args.max_findings,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"ok={str(report['ok']).lower()}")
        print(f"scanned_files={report['scanned_files']}")
        print(f"scanned_artifact_files={report['scanned_artifact_files']}")
        print(f"finding_count={report['finding_count']}")
        if report.get("findings_truncated"):
            print(f"findings_truncated=true returned={report['findings_returned']} max={report['max_findings']}")
        findings = cast(list[dict[str, object]], report["findings"])
        for finding in findings:
            print(
                f"[{finding['check_id']}] {finding['source']}:{finding['path']}:"
                f"{finding['line']} {finding['match_preview']}"
            )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
