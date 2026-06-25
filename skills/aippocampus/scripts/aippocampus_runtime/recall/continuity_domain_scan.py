"""Scan-budget and source-ref helpers for continuity-domain production."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aippocampus_runtime.ops.route_readiness import safe_source_refs
from aippocampus_runtime.recall.query_policy import split_query_terms
from aippocampus_runtime.source.io_kernel import iter_jsonl_dict_rows, load_jsonl_dict_rows
from aippocampus_runtime.source.search import iter_clean_messages

TermsForMessage = Callable[[str, list[str]], tuple[list[str], int, int]]
RegistryTerms = Callable[[Mapping[str, Any]], list[str]]
EntryCleanSourceDir = Callable[[Mapping[str, Any]], Path | None]
PrivacySuppressed = Callable[[str], bool]
SignalTermValues = Callable[[str, Mapping[str, Any]], tuple[list[str], int, int]]


@dataclass
class ContinuityDomainScanResult:
    term_refs: dict[tuple[str, str], list[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )
    term_ref_identities: dict[
        tuple[str, str],
        set[tuple[tuple[str, str], ...]],
    ] = field(default_factory=lambda: defaultdict(set))
    term_co_terms: dict[tuple[str, str], Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    registry_terms_by_thread: dict[str, set[str]] = field(default_factory=dict)
    known_refs: dict[str, dict[str, set[str]]] = field(
        default_factory=lambda: defaultdict(
            lambda: {
                "message_id": set(),
                "turn_id": set(),
                "turn_index": set(),
                "line": set(),
            }
        )
    )
    missing_source_ref_count: int = 0
    privacy_suppressed_terms: set[str] = field(default_factory=set)
    low_information_label_suppressed_count: int = 0
    scanned_thread_count: int = 0
    scanned_message_count: int = 0
    skipped_message_count: int = 0
    skipped_message_count_is_lower_bound: bool = False
    message_budget_truncated_thread_count: int = 0
    message_budget_cutoff_thread_count: int = 0
    source_ref_candidate_count: int = 0
    source_ref_identity_probe_count: int = 0
    source_ref_dedup_hit_count: int = 0
    signal_candidate_count: int = 0


def message_source_ref(thread_key: str, message: Mapping[str, Any]) -> dict[str, Any] | None:
    if not thread_key:
        return None
    ref = {
        "thread_key": thread_key,
        "source_id": message.get("source_id"),
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "line": message.get("source_line") or message.get("line"),
        "phase": message.get("phase"),
    }
    refs = safe_source_refs(ref)
    return refs[0] if refs else None


def remember_ref(
    known_refs: dict[str, dict[str, set[str]]],
    *,
    thread_key: str,
    message: Mapping[str, Any],
) -> None:
    bucket = known_refs[thread_key]
    for key, value in {
        "message_id": message.get("message_id") or message.get("id"),
        "turn_id": message.get("turn_id"),
        "turn_index": message.get("turn_index"),
        "line": message.get("source_line") or message.get("line"),
    }.items():
        if value not in {None, ""}:
            bucket[key].add(str(value))


def ref_resolves(
    ref: Mapping[str, Any],
    *,
    known_refs: Mapping[str, Mapping[str, set[str]]],
) -> bool:
    thread_key = str(ref.get("thread_key") or "")
    if not thread_key:
        return False
    bucket = known_refs.get(thread_key)
    if not bucket:
        return False
    for key in ("message_id", "turn_id", "turn_index", "line"):
        value = ref.get(key)
        if value not in {None, ""} and str(value) in bucket.get(key, set()):
            return True
    return False


def resolving_signal_refs(
    value: Any,
    *,
    known_refs: Mapping[str, Mapping[str, set[str]]],
) -> list[dict[str, Any]]:
    refs = safe_source_refs(value)
    return [ref for ref in refs if ref_resolves(ref, known_refs=known_refs)]


def has_safe_source_refs(value: Any) -> bool:
    return bool(safe_source_refs(value))


def refs_by_thread(refs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_thread: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ref in refs:
        thread_key = str(ref.get("thread_key") or "")
        if thread_key:
            by_thread[thread_key].append(ref)
    return by_thread


@dataclass(frozen=True)
class BudgetedCleanMessages:
    messages: list[dict[str, Any]]
    skipped_message_count: int
    skipped_message_count_is_lower_bound: bool
    cutoff_reached: bool


def load_budgeted_clean_messages(
    path: Path,
    *,
    max_messages: int | None,
) -> BudgetedCleanMessages:
    if max_messages is None:
        return BudgetedCleanMessages(
            messages=list(iter_clean_messages(path)),
            skipped_message_count=0,
            skipped_message_count_is_lower_bound=False,
            cutoff_reached=False,
        )
    limit = max(0, int(max_messages))
    messages: list[dict[str, Any]] = []
    if not path.exists():
        return BudgetedCleanMessages(
            messages=messages,
            skipped_message_count=0,
            skipped_message_count_is_lower_bound=False,
            cutoff_reached=False,
        )
    for row in iter_jsonl_dict_rows(path):
        if len(messages) >= limit:
            # Budgeted foreground previews must stop scanning at the cutoff. We
            # read only the first row past the budget so the operator sees that
            # the scan was partial without paying full long-thread IO just to
            # compute an exact skipped count.
            return BudgetedCleanMessages(
                messages=messages,
                skipped_message_count=1 if row.get("text") else 0,
                skipped_message_count_is_lower_bound=True,
                cutoff_reached=True,
            )
        if row.get("text"):
            messages.append(row)
    return BudgetedCleanMessages(
        messages=messages,
        skipped_message_count=0,
        skipped_message_count_is_lower_bound=False,
        cutoff_reached=False,
    )


def source_ref_identity(ref: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    identity = tuple(
        (key, str(ref.get(key)))
        for key in (
            "thread_key",
            "source_id",
            "message_id",
            "turn_id",
            "turn_index",
            "line",
            "phase",
        )
        if ref.get(key) not in {None, ""}
    )
    if identity:
        return identity
    return tuple((key, str(value)) for key, value in sorted(ref.items()))


def append_ordered_unique_ref(
    term_refs: dict[tuple[str, str], list[dict[str, Any]]],
    term_ref_identities: dict[tuple[str, str], set[tuple[tuple[str, str], ...]]],
    key: tuple[str, str],
    ref: dict[str, Any],
) -> bool:
    identity = source_ref_identity(ref)
    identities = term_ref_identities[key]
    if identity in identities:
        return False
    identities.add(identity)
    term_refs[key].append(ref)
    return True


def collect_continuity_domain_scan(
    *,
    threads: Sequence[Mapping[str, Any]],
    registry_root: Path,
    signal_candidate_files: Sequence[str],
    max_messages_per_thread: int | None,
    entry_clean_source_dir: EntryCleanSourceDir,
    registry_terms_for_entry: RegistryTerms,
    privacy_suppressed_term: PrivacySuppressed,
    terms_for_message: TermsForMessage,
    signal_term_values: SignalTermValues,
) -> ContinuityDomainScanResult:
    result = ContinuityDomainScanResult()
    for entry in threads:
        thread_key = str(entry.get("thread_key") or "").strip()
        clean_dir = entry_clean_source_dir(entry)
        if not thread_key or clean_dir is None:
            continue
        result.scanned_thread_count += 1
        registry_terms = registry_terms_for_entry(entry)
        result.registry_terms_by_thread[thread_key] = {
            term.casefold() for term in registry_terms
        }
        budgeted = load_budgeted_clean_messages(
            clean_dir / "messages.jsonl",
            max_messages=max_messages_per_thread,
        )
        messages = budgeted.messages
        result.skipped_message_count += budgeted.skipped_message_count
        result.skipped_message_count_is_lower_bound = (
            result.skipped_message_count_is_lower_bound
            or budgeted.skipped_message_count_is_lower_bound
        )
        if budgeted.cutoff_reached:
            result.message_budget_cutoff_thread_count += 1
            result.message_budget_truncated_thread_count += 1
        for message in messages:
            result.scanned_message_count += 1
            text = str(message.get("text") or "")
            if not text:
                continue
            remember_ref(result.known_refs, thread_key=thread_key, message=message)
            if privacy_suppressed_term(thread_key):
                result.missing_source_ref_count += 1
                continue
            ref = message_source_ref(thread_key, message)
            if ref is None:
                result.missing_source_ref_count += 1
                continue
            terms, suppressed_count, low_information_count = terms_for_message(
                text, registry_terms
            )
            if suppressed_count:
                result.privacy_suppressed_terms.update(
                    split_query_terms([text])[:suppressed_count]
                )
            result.low_information_label_suppressed_count += low_information_count
            for term in terms:
                key = (thread_key, term)
                result.source_ref_candidate_count += 1
                result.source_ref_identity_probe_count += 1
                if not append_ordered_unique_ref(
                    result.term_refs,
                    result.term_ref_identities,
                    key,
                    ref,
                ):
                    result.source_ref_dedup_hit_count += 1
                result.term_co_terms[key].update(other for other in terms if other != term)

    for file_name in signal_candidate_files:
        for row in load_jsonl_dict_rows(registry_root / file_name).rows:
            raw_refs = (
                row.get("source_refs")
                or row.get("source_ref")
                or row.get("representative_sources")
            )
            refs = resolving_signal_refs(raw_refs, known_refs=result.known_refs)
            if not refs:
                if has_safe_source_refs(raw_refs):
                    result.missing_source_ref_count += 1
                continue
            terms, suppressed_count, low_information_count = signal_term_values(file_name, row)
            result.privacy_suppressed_terms.update(
                f"signal:{file_name}:{index}" for index in range(suppressed_count)
            )
            result.low_information_label_suppressed_count += low_information_count
            for thread_key, thread_refs in refs_by_thread(refs).items():
                for term in terms:
                    key = (thread_key, term)
                    for ref in thread_refs:
                        result.source_ref_candidate_count += 1
                        result.source_ref_identity_probe_count += 1
                        if not append_ordered_unique_ref(
                            result.term_refs,
                            result.term_ref_identities,
                            key,
                            ref,
                        ):
                            result.source_ref_dedup_hit_count += 1
                    result.term_co_terms[key].update(other for other in terms if other != term)
                    result.signal_candidate_count += 1
    return result


__all__ = [
    "append_ordered_unique_ref",
    "collect_continuity_domain_scan",
    "ContinuityDomainScanResult",
    "has_safe_source_refs",
    "load_budgeted_clean_messages",
    "message_source_ref",
    "refs_by_thread",
    "remember_ref",
    "resolving_signal_refs",
    "source_ref_identity",
]
