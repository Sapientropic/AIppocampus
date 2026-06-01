#!/usr/bin/env python3
"""Benchmark AIppocampus foreground memory-decision behavior.

This Track A runner measures the prompt-hook decision surface: skip, scent, or
evidence. It intentionally keeps the first fixture synthetic and deterministic
so CI can catch over-escalation and privacy regressions without live LLM calls
or private registry text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import _paths

_paths.ensure_paths()

import aippocampus_prompt_hook as hook
from benchmark_statistics import binomial_rate_report
from build_index import make_sqlite

EXPECTED_LABELS = {"should_skip", "should_scent", "should_evidence"}
EXPECTED_TO_ACTUAL = {
    "should_skip": "skip",
    "should_scent": "scent",
    "should_evidence": "evidence",
}
ACTUAL_DECISIONS = {"skip", "scent", "evidence"}
SCHEMA_VERSION = 1
SOURCE_FREE_TWIN_FORBIDDEN_TERMS = (
    "can you cite",
    "cite",
    "citation",
    "clean source",
    "evidence",
    "source-backed",
    "source evidence",
    "source-backed evidence",
    "verbatim",
    "quote",
    "原话",
    "原文",
    "引用",
    "证据",
    "行号",
)
EXACT_ALIAS_ABLATION_TERMS = (
    "external hippocampus",
    "source-backed",
    "source-backed memory",
    "raw history",
    "AIppocampus Atlas",
    "Atlas recall gate",
    "same-name entity trap",
)
DEFAULT_SHAREGPT_CORPUS_DIR = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "output"
    / "sharegpt_coding_multiturn"
).resolve()
CODING_CUE_STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "before",
    "could",
    "error",
    "function",
    "handle",
    "help",
    "missing",
    "please",
    "problem",
    "return",
    "should",
    "thanks",
    "using",
    "what",
    "when",
    "where",
    "with",
    "would",
}


@dataclass(frozen=True)
class MemoryPainFixture:
    family: str
    category: str
    track: str
    public_sources: tuple[str, ...]
    expectation: str
    validation_note: str


MEMORY_PAIN_FIXTURES: dict[str, MemoryPainFixture] = {
    "write_time_pollution": MemoryPainFixture(
        family="write_time_pollution",
        category="Write-time pollution",
        track="Track A",
        public_sources=("Mem0 #4573", "Mem0 #4099"),
        expectation="unsupported_not_evidence",
        validation_note="Boot/system text can scent a nearby context but must not become evidence.",
    ),
    "recalled_context_feedback_loop": MemoryPainFixture(
        family="recalled_context_feedback_loop",
        category="Write-time pollution",
        track="Track A",
        public_sources=("Mem0 #4573",),
        expectation="unsupported_not_evidence",
        validation_note="Recalled text echoed back into the prompt is not new source support.",
    ),
    "fabricated_profile_no_source": MemoryPainFixture(
        family="fabricated_profile_no_source",
        category="Write-time pollution",
        track="Track A",
        public_sources=("Mem0 #4099",),
        expectation="unsupported_not_evidence",
        validation_note="Model-inferred profile traits stay unsupported without clean-source refs.",
    ),
    "transient_task_state": MemoryPainFixture(
        family="transient_task_state",
        category="Write-time pollution",
        track="Track A",
        public_sources=("Mem0 #4573",),
        expectation="unsupported_not_evidence",
        validation_note="Ephemeral run state can be current context, not durable memory evidence.",
    ),
    "deterministic_vs_fuzzy_memory": MemoryPainFixture(
        family="deterministic_vs_fuzzy_memory",
        category="Deterministic memory vs fuzzy recall",
        track="Track A",
        public_sources=("Mem0 #4926", "HN item 46891715"),
        expectation="unsupported_not_evidence",
        validation_note="Durable preferences and ambient hints must remain separate surfaces.",
    ),
    "metadata_round_trip": MemoryPainFixture(
        family="metadata_round_trip",
        category="Metadata/provenance round-trip",
        track="Track C",
        public_sources=("Mem0 #5055",),
        expectation="unsupported_not_evidence",
        validation_note="Caller metadata labels are not source truth and must not be rewritten.",
    ),
    "large_document_no_foreground_llm": MemoryPainFixture(
        family="large_document_no_foreground_llm",
        category="Eager LLM extraction cost and scale",
        track="Track B",
        public_sources=("Graphiti #1516", "Graphiti #1262", "Graphiti #1275", "Graphiti #1193"),
        expectation="unsupported_not_evidence",
        validation_note="Large canonical source retrieval must not require foreground LLM extraction.",
    ),
    "invalid_structured_extraction": MemoryPainFixture(
        family="invalid_structured_extraction",
        category="Invalid structured extraction",
        track="Track C",
        public_sources=("Graphiti #760",),
        expectation="unsupported_not_evidence",
        validation_note="Plausible structured facts remain advisory until source-backed.",
    ),
    "compaction_continuity": MemoryPainFixture(
        family="compaction_continuity",
        category="Compaction continuity failure",
        track="Track D seed",
        public_sources=("Letta #3270", "Letta #3242", "Letta #3279"),
        expectation="unsupported_not_evidence",
        validation_note="Compaction summaries must not claim continuity when corrections are missing.",
    ),
}


@dataclass(frozen=True)
class GateCase:
    case_id: str
    case_type: str
    expected: str
    prompt: str
    search_budget: int = 0
    use_semantic_gate: bool = False
    semantic_gate_fixture: str = "disabled"
    working_memory: bool = False
    cwd_role: str = "workspace"
    expected_evidence_thread_key: str | None = None
    memory_pain_family: str | None = None
    semantic_trigger_alias_mode: str = "full"

    def to_result_stub(self, *, include_private_text: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "case_id": self.case_id,
            "case_type": self.case_type,
            "expected": self.expected,
            "prompt_sha1": sha1_text(self.prompt)[:16],
            "search_budget": self.search_budget,
            "use_semantic_gate": self.use_semantic_gate,
            "semantic_gate_fixture": self.semantic_gate_fixture,
            "semantic_trigger_alias_mode": self.semantic_trigger_alias_mode,
            "uses_working_memory": self.working_memory,
            "cwd_role": self.cwd_role,
        }
        if self.memory_pain_family:
            fixture = MEMORY_PAIN_FIXTURES[self.memory_pain_family]
            payload.update(
                {
                    "memory_pain_family": fixture.family,
                    "memory_pain_category": fixture.category,
                    "memory_pain_track": fixture.track,
                    "memory_pain_expectation": fixture.expectation,
                    "public_sources": list(fixture.public_sources),
                }
            )
        if include_private_text:
            payload["prompt"] = self.prompt
        return payload


@dataclass(frozen=True)
class SyntheticFixture:
    root: Path
    workspace: Path
    registry_path: Path
    working_memory_path: Path
    cases: list[GateCase]
    other_workspace: Path | None = None
    semantic_triggers_path: Path | None = None
    semantic_triggers_ablated_path: Path | None = None


@dataclass(frozen=True)
class SourceFreeTwinFixture:
    twin: str
    evidence_prompt: str
    scent_prompt: str
    expected_evidence_thread_key: str
    required_topic_terms: tuple[str, ...]
    expected_support_level: str = "scent"
    forbidden_source_request_terms: tuple[str, ...] = SOURCE_FREE_TWIN_FORBIDDEN_TERMS

    def validate(self) -> None:
        """Guard explicit same-topic twins from drifting back to source requests."""

        if self.expected_support_level != "scent":
            raise ValueError(f"{self.twin}: source-free twin must expect scent")
        if not self.required_topic_terms:
            raise ValueError(f"{self.twin}: required_topic_terms must not be empty")
        if self.evidence_prompt.strip() == self.scent_prompt.strip():
            raise ValueError(f"{self.twin}: scent twin must be an explicit rewrite")
        scent_low = self.scent_prompt.casefold()
        forbidden = [
            term
            for term in self.forbidden_source_request_terms
            if term.casefold() in scent_low
        ]
        if forbidden:
            raise ValueError(f"{self.twin}: scent twin kept source request terms {forbidden}")
        if not any(term in self.scent_prompt for term in self.required_topic_terms):
            raise ValueError(f"{self.twin}: scent twin lost required topic terms")


def source_free_scent_twin_fixtures() -> list[SourceFreeTwinFixture]:
    """Explicit evidence/scent pairs for support-level routing tests.

    These prompts are hand-written fixture contracts, not runtime semantic
    policy. The invariant list below only prevents the benchmark from rewarding
    itself for leaving source-request wording in a should-scent case.
    """

    return [
        SourceFreeTwinFixture(
            twin="quote_exact",
            evidence_prompt="找回 生命还能变成什么 而我能不能仍然是我 那句原话。",
            scent_prompt="生命还能变成什么，而我能不能仍然是我，这个自我连续性的方向继续想。",
            expected_evidence_thread_key="session:synthetic-memory",
            required_topic_terms=("生命还能变成什么", "自我连续性"),
        ),
        SourceFreeTwinFixture(
            twin="raw_history_exact",
            evidence_prompt="找回 raw history 明明在本地 需要外置海马体 那句原话。",
            scent_prompt="本地历史被压缩后不好定位，这个可重开的来源层继续想。",
            expected_evidence_thread_key="session:synthetic-memory",
            required_topic_terms=("本地历史", "来源层"),
        ),
        SourceFreeTwinFixture(
            twin="atlas_current_exact",
            evidence_prompt="找回 AIppocampus Atlas recall gate project-scoped 那句原话。",
            scent_prompt="AIppocampus 里那个项目作用域召回边界继续想。",
            expected_evidence_thread_key="session:atlas-current-project",
            required_topic_terms=("AIppocampus", "项目作用域"),
        ),
        SourceFreeTwinFixture(
            twin="atlas_other_exact",
            evidence_prompt="找回 Atlas dashboard project different entity 那句原话。",
            scent_prompt="另一个 dashboard 项目的同名 Atlas 边界继续想。",
            expected_evidence_thread_key="session:atlas-other-project",
            required_topic_terms=("dashboard", "Atlas"),
        ),
        SourceFreeTwinFixture(
            twin="atlas_current_line",
            evidence_prompt="Can you cite AIppocampus Atlas recall gate should stay project-scoped?",
            scent_prompt="AIppocampus 里那个项目作用域召回边界，继续收一下。",
            expected_evidence_thread_key="session:atlas-current-project",
            required_topic_terms=("AIppocampus", "项目作用域"),
        ),
        SourceFreeTwinFixture(
            twin="atlas_other_line",
            evidence_prompt="Can you cite Atlas dashboard project uses a different entity?",
            scent_prompt="另一个 dashboard 项目里同名 Atlas 的边界，继续收一下。",
            expected_evidence_thread_key="session:atlas-other-project",
            required_topic_terms=("dashboard", "Atlas"),
        ),
        SourceFreeTwinFixture(
            twin="hippocampus_source",
            evidence_prompt="请给 source-backed evidence：raw history 明明在本地。",
            scent_prompt="本地历史需要一个可重开的来源层，这个方向继续想。",
            expected_evidence_thread_key="session:synthetic-memory",
            required_topic_terms=("本地历史", "来源层"),
        ),
        SourceFreeTwinFixture(
            twin="life_quote_source",
            evidence_prompt="请给 source evidence：生命还能变成什么。",
            scent_prompt="生命还能变成什么这条自我连续性线索继续想。",
            expected_evidence_thread_key="session:synthetic-memory",
            required_topic_terms=("生命还能变成什么", "自我连续性"),
        ),
    ]


def source_free_scent_twin_prompt(prompt: str) -> str:
    """Convert an evidence prompt into a same-topic scent-only twin.

    These twins test support-level routing, so they must remove source-request
    wording. Leaving "cite" or "那句原话" in a should_scent case makes the
    benchmark punish correct evidence behavior rather than over-escalation.
    """

    text = prompt.strip()
    cite_match = re.match(r"Can you cite\s+(.+?)\??$", text, flags=re.IGNORECASE)
    if cite_match:
        return f"{cite_match.group(1)} 这条线继续想。"
    text = text.replace("找回", "继续想")
    text = text.replace("请给 source-backed evidence：", "")
    text = text.replace("请给 source evidence：", "")
    text = text.replace("source-backed evidence", "source-backed memory")
    text = text.replace("source evidence", "source context")
    text = text.replace("那句原话", "这个方向")
    text = text.replace("这句原话", "这个方向")
    text = text.replace("原话", "线索")
    text = text.replace("原文", "线索")
    return text


def build_harder_synthetic_case_bank() -> list[GateCase]:
    """Build deterministic adversarial Track A cases.

    The bank is intentionally synthetic, but not fixture-easy. Cases are grouped
    into twins so the same surface tokens can mean skip, scent, or evidence
    depending on memory intent, project scope, semantic behavior, and evidence
    budget. This keeps future "helpful" cue-list edits from silently turning
    ordinary work prompts into memory prompts, or turning vague scent into source
    snippets.
    """

    cases: list[GateCase] = []

    def add(
        twin: str,
        role: str,
        family: str,
        expected: str,
        prompt: str,
        *,
        search_budget: int = 0,
        use_semantic_gate: bool = False,
        semantic_gate_fixture: str = "disabled",
        working_memory: bool = False,
        cwd_role: str = "workspace",
        expected_evidence_thread_key: str | None = None,
        semantic_trigger_alias_mode: str = "full",
    ) -> None:
        cases.append(
            GateCase(
                case_id=f"synthetic_hard_bank__{twin}__{role}",
                case_type=f"hard_bank_{family}",
                expected=expected,
                prompt=prompt,
                search_budget=search_budget,
                use_semantic_gate=use_semantic_gate,
                semantic_gate_fixture=semantic_gate_fixture,
                working_memory=working_memory,
                cwd_role=cwd_role,
                expected_evidence_thread_key=expected_evidence_thread_key,
                semantic_trigger_alias_mode=semantic_trigger_alias_mode,
            )
        )

    hard_negative_prompts = [
        ("atlas_layout", "把 Atlas dashboard layout 的间距和 charts legend 调一下。"),
        ("atlas_copy", "Atlas dashboard 这个 card copy 先收短一点，别动数据。"),
        ("atlas_button", "Atlas dashboard 的按钮 hover 态和 loading 态一起改。"),
        ("atlas_grid", "Atlas dashboard grid 断点重新排一下，mobile 别挤。"),
        ("atlas_panel", "Atlas panel 的 filters 和 charts 对齐一下。"),
        ("atlas_route", "Atlas route 里的 dashboard shell 先接上。"),
        ("atlas_table", "Atlas dashboard table column width 做个固定值。"),
        ("atlas_theme", "Atlas dashboard theme token 换成现有变量。"),
        ("atlas_modal", "Atlas dashboard modal 的 close button 修一下。"),
        ("atlas_fixture", "Atlas dashboard fixture 里多补两个 chart 状态。"),
        ("atlas_style", "Atlas layout sprint 这版视觉稿先按 Figma 还原。"),
        ("atlas_nav", "Atlas navigation 里的 dashboard tab 高亮不对，修掉。"),
    ]
    for twin, prompt in hard_negative_prompts:
        add(
            twin,
            "skip_high_overlap",
            "hard_negative_high_overlap",
            "should_skip",
            prompt,
            search_budget=2,
        )
        add(
            twin,
            "scent_same_tokens",
            "scent_cross_project_trap",
            "should_scent",
            f"{prompt} 但先只继续 Atlas 那条上下文，不要展开实现。",
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="positive_scent",
            cwd_role="other_project" if twin.endswith(("layout", "grid", "theme")) else "workspace",
        )

    false_cue_code_prompts = [
        ("parse_case", "记住这个函数名 parseCaseId，然后把失败测试修掉。"),
        ("hook_test", "remember the hook test helper name, then update the assertion."),
        ("evidence_var", "把 evidencePanel 组件的空状态改一下，不要查历史。"),
        ("source_map", "sourceMapLoader 报错了，先修编译。"),
        ("recall_button", "RecallButton 的 hover 样式坏了，改一下 CSS。"),
        ("memory_cache", "MemoryCache 类的 TTL 单测挂了，先补 mock。"),
        ("quote_widget", "QuoteWidget snapshot 不稳定，记一下变量名就行。"),
        ("last_reply_fn", "lastReplyFormatter 这个函数重命名，顺手跑 test。"),
    ]
    for twin, prompt in false_cue_code_prompts:
        add(
            twin,
            "skip_false_cue",
            "false_cue_code_surface",
            "should_skip",
            prompt,
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="timeout",
        )
        add(
            twin,
            "scent_memory_intent",
            "semantic_overevidence_trap",
            "should_scent",
            f"{prompt} 另外 external hippocampus hook 那条线继续想一下。",
            search_budget=3,
            use_semantic_gate=True,
            semantic_gate_fixture="overeager_evidence",
        )

    secret_like_prompts = [
        ("token_rotate", "Rotate the API token placeholder in settings and update the test."),
        ("cookie_mock", "cookie mock 里那个 session placeholder 换个名字。"),
        ("oauth_secret", "OAuth secret placeholder 的 label 太长，收一下。"),
        ("env_sample", "env.sample 里的 ACCESS_TOKEN placeholder 排版错了。"),
        ("private_key", "private key placeholder 文案改成 sentence case。"),
        ("webhook_sig", "webhook signature placeholder 的 validation 文案修一下。"),
        ("db_password", "database password placeholder 不要显示在 UI 里。"),
        ("bearer_header", "Bearer header placeholder 的 fixture 名字太误导。"),
    ]
    for twin, prompt in secret_like_prompts:
        add(
            twin,
            "skip_secret_surface",
            "secret_like_suppression",
            "should_skip",
            prompt,
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="overeager_evidence",
        )
        add(
            twin,
            "scent_safe_memory_boundary",
            "budget_timeout_degrade",
            "should_scent",
            f"{prompt} 但只看外置海马体边界，不要展开任何 secret value。",
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="timeout",
        )

    cross_project_prompts = [
        ("atlas_current_scope", "AIppocampus 里的 Atlas recall gate 继续，先别引用原文。", "workspace"),
        ("atlas_other_scope", "Atlas dashboard layout sprint 继续，先别引用原文。", "other_project"),
        ("atlas_current_hook", "AIppocampus Atlas hook scope 这条线继续想。", "workspace"),
        ("atlas_other_charts", "Atlas charts layout 那个方向继续推进。", "other_project"),
        ("atlas_current_boundary", "AIppocampus Atlas project-scoped boundary 继续。", "workspace"),
        ("atlas_other_entity", "Atlas dashboard same-name entity trap 继续看。", "other_project"),
        ("atlas_current_gate", "Atlas recall gate 在 AIppocampus 里继续，不给 source。", "workspace"),
        ("atlas_other_grid", "Atlas dashboard grid sprint 继续，不给 source。", "other_project"),
    ]
    for twin, prompt, cwd_role in cross_project_prompts:
        add(
            twin,
            "scent_budgeted_scope",
            "scent_cross_project_trap",
            "should_scent",
            prompt,
            search_budget=3,
            use_semantic_gate=True,
            semantic_gate_fixture="positive_scent",
            cwd_role=cwd_role,
        )
        add(
            twin,
            "skip_plain_action",
            "hard_negative_high_overlap",
            "should_skip",
            prompt.replace("继续", "实现").replace("先别引用原文", "顺手跑测试"),
            search_budget=2,
            cwd_role=cwd_role,
        )

    semantic_traps = [
        ("hippocampus_line", "external hippocampus hook 那条线先继续推进。"),
        ("ambient_line", "ambient recall 前台提示这块继续收口。"),
        ("active_line", "active recall 和触发式联想的边界继续想。"),
        ("source_backed_line", "source-backed memory 的味道先给我，不要引用。"),
        ("raw_history_line", "raw history 明明在本地这条线继续。"),
        ("continuity_line", "self-continuity quote 那个方向继续。"),
        ("prompt_hook_line", "prompt hook 预算放开后的效果继续看。"),
        ("recall_gate_line", "recall gate 的 scent-only 边界继续。"),
    ]
    for twin, prompt in semantic_traps:
        add(
            twin,
            "scent_semantic_overeager",
            "semantic_overevidence_trap",
            "should_scent",
            prompt,
            search_budget=3,
            use_semantic_gate=True,
            semantic_gate_fixture="overeager_evidence",
        )
        add(
            twin,
            "evidence_explicit_twin",
            "competing_source_evidence",
            "should_evidence",
            prompt.replace("继续", "找回").replace("不要引用", "给原话"),
            search_budget=2,
            expected_evidence_thread_key="session:synthetic-memory"
            if twin
            in {
                "hippocampus_line",
                "source_backed_line",
                "raw_history_line",
                "continuity_line",
                "prompt_hook_line",
            }
            else "session:atlas-current-project",
        )

    for twin_fixture in source_free_scent_twin_fixtures():
        twin_fixture.validate()
        add(
            twin_fixture.twin,
            "evidence_competing_source",
            "competing_source_evidence",
            "should_evidence",
            twin_fixture.evidence_prompt,
            search_budget=3,
            expected_evidence_thread_key=twin_fixture.expected_evidence_thread_key,
        )
        add(
            twin_fixture.twin,
            "scent_no_source_twin",
            "semantic_overevidence_trap",
            "should_" + twin_fixture.expected_support_level,
            twin_fixture.scent_prompt,
            search_budget=3,
            use_semantic_gate=True,
            semantic_gate_fixture="overeager_evidence",
        )

    alias_ablation_prompts = [
        (
            "recoverable_source_layer",
            "scent_semantic_paraphrase",
            "should_scent",
            "我们之前说的可重开来源层，继续收一下，只要方向。",
            "paraphrase_scent",
            None,
        ),
        (
            "local_history_boundary",
            "scent_semantic_paraphrase",
            "should_scent",
            "本地历史被压缩后不好定位，这个边界继续想。",
            "paraphrase_scent",
            None,
        ),
        (
            "project_scope_wording",
            "evidence_semantic_paraphrase",
            "should_evidence",
            "之前关于记忆项目里那个同名计划边界怎么说来着？",
            "paraphrase_project_evidence",
            "session:atlas-current-project",
        ),
        (
            "project_scope_boundary",
            "scent_project_paraphrase",
            "should_scent",
            "记忆项目里那个同名计划边界继续收一下，只要方向。",
            "paraphrase_project_scent",
            None,
        ),
    ]
    for twin, role, expected, prompt, semantic_fixture, thread_key in alias_ablation_prompts:
        add(
            twin,
            role,
            "alias_ablation",
            expected,
            prompt,
            search_budget=3 if expected == "should_evidence" else 2,
            use_semantic_gate=True,
            semantic_gate_fixture=semantic_fixture,
            expected_evidence_thread_key=thread_key,
            semantic_trigger_alias_mode="ablated",
        )

    multilingual_prompts = [
        ("zh_en_hook", "Can we 继续 external hippocampus 的 prompt hook 线索?"),
        ("zh_en_gate", "这个 recall gate 能不能 stay project-scoped?"),
        ("zh_en_raw", "raw history 明明在本地, why did the hook miss it?"),
        ("zh_en_continuity", "self-continuity 那句 quote 还要怎么处理?"),
        ("zh_en_atlas", "AIppocampus Atlas 这条 same-name entity trap 怎么收?"),
        ("zh_en_source", "source-backed 但先只给 scent, 不要原话。"),
        ("zh_en_budget", "live semantic eval 中文 continuation 为什么波动?"),
        ("zh_en_scope", "cwd 和 project scope 冲突时该怎么 scent?"),
    ]
    for twin, prompt in multilingual_prompts:
        add(
            twin,
            "scent_multilingual",
            "multilingual_paraphrase",
            "should_scent",
            prompt,
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="positive_scent",
        )
        add(
            twin,
            "evidence_multilingual",
            "multilingual_paraphrase",
            "should_evidence",
            "请给 source-backed evidence："
            + prompt.replace("继续", "找回").replace("先只给 scent, 不要原话", "给原话")
            + " raw history 明明在本地",
            search_budget=2,
            expected_evidence_thread_key="session:synthetic-memory",
        )

    budget_prompts = [
        ("budget_hook", "external hippocampus hook 这条线继续，但 semantic 可能 timeout。"),
        ("budget_atlas", "AIppocampus Atlas recall gate 继续，但 live model 可能慢。"),
        ("budget_raw", "raw history 明明在本地这个问题继续，但别等太久。"),
        ("budget_active", "active recall 的 foreground hook 继续收，不要拿证据。"),
        ("budget_continuity", "self-continuity 这条线继续，semantic 挂了也给 scent。"),
        ("budget_scope", "project-scoped memory boundary 继续，semantic 超时也别乱给 evidence。"),
    ]
    for twin, prompt in budget_prompts:
        add(
            twin,
            "scent_timeout_degrade",
            "budget_timeout_degrade",
            "should_scent",
            prompt,
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="timeout",
        )
        add(
            twin,
            "skip_timeout_plain_task",
            "budget_timeout_degrade",
            "should_skip",
            prompt.replace("继续", "实现").replace("memory boundary", "settings panel"),
            search_budget=2,
            use_semantic_gate=True,
            semantic_gate_fixture="timeout",
        )

    natural_oral_prompts = [
        ("plain_button", "skip_plain_task", "should_skip", "这个按钮又歪了，先帮我修一下。"),
        ("plain_bug_pause", "skip_plain_task", "should_skip", "上次那个 bug 先别管，先把 failing test 跑通。"),
        ("remember_var", "skip_plain_task", "should_skip", "我说记住这个变量名，不是让你写记忆。"),
        ("atlas_modal", "skip_plain_task", "should_skip", "Atlas 那个 modal close button 先改一下。"),
        ("list_sort_copy", "skip_plain_task", "should_skip", "帮我把 list.sort 这个 demo 里的 copy 改顺。"),
        ("no_history_copy", "skip_plain_task", "should_skip", "别查历史，直接把 dashboard 空状态文案换掉。"),
        ("timeout_test", "skip_plain_task", "should_skip", "这个 timeout test 太慢了，先调 fixture。"),
        ("cookie_placeholder", "skip_plain_task", "should_skip", "cookie placeholder 名字换一下，不要碰真实值。"),
        ("bug_card_spacing", "skip_plain_task", "should_skip", "把 bugReportCard 的间距收一下。"),
        ("source_map_compile", "skip_plain_task", "should_skip", "这段 source map 错不是历史问题，直接修编译。"),
        ("atlas_direction", "scent_oral_continuation", "should_scent", "上次那个 Atlas 方向先接着想，不用翻原文。"),
        ("hippocampus_continue", "scent_oral_continuation", "should_scent", "我们前面聊的外置海马体那块，继续推进就行。"),
        ("hook_active", "scent_oral_continuation", "should_scent", "刚才说的 hook 主动一点，这条线继续。"),
        ("continuity_feel", "scent_oral_continuation", "should_scent", "那个 self-continuity 的感觉还在，先接着想。"),
        ("gate_boundary", "scent_oral_continuation", "should_scent", "AIppocampus 这个 recall gate 边界再收一下。"),
        ("atlas_not_dashboard", "scent_oral_continuation", "should_scent", "Atlas 不是 dashboard 那个，是记忆这边，继续看。"),
        ("zh_continuation", "scent_oral_continuation", "should_scent", "上次那个中文 continuation miss 先继续复盘，不要找证据。"),
        ("scope_boundary", "scent_oral_continuation", "should_scent", "project-scoped memory boundary 这块我们继续。"),
        ("bug_wording", "evidence_oral_recall", "should_evidence", "上次那个 bug 怎么说的来着？"),
        ("top28_bug", "evidence_oral_recall", "should_evidence", "之前说 top 28 registry entries 那个问题，是怎么定性的？"),
        ("zh_template_bug", "evidence_oral_recall", "should_evidence", "中文 continuation miss 那次到底是哪句模板的问题？"),
        ("raw_history", "evidence_oral_recall", "should_evidence", "raw history 明明在本地那段怎么说来着？"),
        ("external_hippocampus", "evidence_oral_recall", "should_evidence", "外置海马体那句是怎么说的来着？"),
        ("life_quote", "evidence_oral_recall", "should_evidence", "生命还能变成什么那句你帮我找一下。"),
        ("atlas_project_scoped", "evidence_oral_recall", "should_evidence", "AIppocampus Atlas project-scoped 那句怎么说来着？"),
        ("atlas_other_entity", "evidence_oral_recall", "should_evidence", "Atlas dashboard different entity 那句怎么说来着？"),
        ("scent_boundary", "evidence_oral_recall", "should_evidence", "上次我们说 ambiguous continuation 和 evidence 的边界怎么表述？"),
        ("hook_budget", "evidence_oral_recall", "should_evidence", "prompt hook 预算放开后的那个结论怎么说来着？"),
        ("source_vs_scent", "evidence_oral_recall", "should_evidence", "source-backed memory 和 scent 的区别我们怎么说的？"),
        ("fixture_boundary", "evidence_oral_recall", "should_evidence", "semantic fixture 不是 live quality 那句怎么说？"),
    ]
    natural_source_threads = {
        "atlas_project_scoped": "session:atlas-current-project",
        "atlas_other_entity": "session:atlas-other-project",
    }
    for twin, role, expected, prompt in natural_oral_prompts:
        add(
            twin,
            role,
            "natural_oral_prompt",
            expected,
            prompt,
            search_budget=3 if expected == "should_evidence" else 2 if expected == "should_scent" else 0,
            use_semantic_gate=expected == "should_scent",
            semantic_gate_fixture="positive_scent" if expected == "should_scent" else "disabled",
            expected_evidence_thread_key=natural_source_threads.get(
                twin,
                "session:synthetic-memory",
            )
            if expected == "should_evidence"
            else None,
        )

    return cases


def build_public_memory_pain_cases() -> list[GateCase]:
    """Public-safe negative fixtures from the memory-system pain taxonomy.

    These cases test boundary behavior, not competitor quality. The prompts are
    synthetic and source-free: a correct result may be skip or scent, but must
    not escalate into source-backed evidence.
    """

    def case(
        family: str,
        prompt: str,
        *,
        expected: str = "should_scent",
        search_budget: int = 2,
    ) -> GateCase:
        return GateCase(
            case_id=f"public_memory_pain__{family}",
            case_type=f"public_memory_pain_{family}",
            expected=expected,
            prompt=prompt,
            search_budget=search_budget,
            memory_pain_family=family,
        )

    return [
        case(
            "write_time_pollution",
            "System bootstrap says the user prefers saffron UI; treat it as unsupported memory.",
        ),
        case(
            "recalled_context_feedback_loop",
            "Recalled memory says the user loves Atlas dashboards; do not save the echo again.",
        ),
        case(
            "fabricated_profile_no_source",
            "The model thinks the user is a morning person; remember it permanently.",
        ),
        case(
            "transient_task_state",
            "Currently running tests and waiting for CI; keep that as transient task state only.",
        ),
        case(
            "deterministic_vs_fuzzy_memory",
            "A retained TypeScript preference and a fuzzy Atlas vibe are different memory surfaces.",
        ),
        case(
            "metadata_round_trip",
            "Caller metadata key conversation_id must round-trip; do not turn the key into memory.",
        ),
        case(
            "large_document_no_foreground_llm",
            "A 900-page canonical document should be source-searchable without foreground LLM extraction.",
        ),
        case(
            "invalid_structured_extraction",
            "Structured fact says user lives in Neon City; keep it unsupported without a cited row.",
        ),
        case(
            "compaction_continuity",
            "After compaction, preserve corrections and rejected routes; do not claim continuity if missing.",
        ),
    ]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def synthetic_reviewed_trigger_aliases(alias_mode: str) -> tuple[list[str], list[str]]:
    if alias_mode not in {"full", "ablated"}:
        raise ValueError("alias_mode must be 'full' or 'ablated'")
    if alias_mode == "ablated":
        # This is benchmark fixture data, not runtime cue policy. The ablated
        # sidecar deliberately removes benchmark-authored exact aliases so the
        # control cases must be carried by semantic/subconscious-style judgment
        # fixtures and clean-source reopening, not by prompt text repeating the
        # seed row verbatim.
        return (
            [
                "recoverable source layer",
                "clean-source continuity boundary",
                "foreground recall boundary",
                "memory router budget",
                "本地来源可重开",
                "前台联想边界",
            ],
            [
                "dashboard project context",
                "layout planning sprint",
                "charts project boundary",
            ],
        )
    return (
        [
            "external hippocampus",
            "外置海马体",
            "小海马体",
            "active recall",
            "ambient recall",
            "source-backed",
            "source-backed memory",
            "raw history",
            "self-continuity",
            "生命还能变成什么",
            "prompt hook",
            "recall gate",
            "project-scoped",
            "scent-only",
            "AIppocampus Atlas",
            "Atlas recall gate",
            "same-name entity trap",
            "cwd",
            "project scope",
        ],
        [
            "Atlas dashboard",
            "Atlas dashboard layout",
            "layout sprint",
            "charts",
            "same-name entity trap",
        ],
    )


def write_synthetic_reviewed_semantic_triggers(
    registry_path: Path,
    *,
    alias_mode: str = "full",
    filename: str = "semantic_triggers.jsonl",
) -> Path:
    memory_aliases, atlas_aliases = synthetic_reviewed_trigger_aliases(alias_mode)
    memory_title = (
        "AIppocampus recoverable source boundary"
        if alias_mode == "ablated"
        else "AIppocampus external hippocampus and recall gate"
    )
    memory_when_to_use = (
        "Use when the benchmark prompt asks to continue AIppocampus continuity, "
        "recoverable source-layer, or project-boundary context."
        if alias_mode == "ablated"
        else (
            "Use when the benchmark prompt asks to continue AIppocampus "
            "memory architecture, recall-gate, source-backed, or project-scope context."
        )
    )
    atlas_title = (
        "Dashboard project context"
        if alias_mode == "ablated"
        else "Atlas dashboard same-name project context"
    )
    atlas_when_to_use = (
        "Use only when the prompt asks to continue the dashboard project context "
        "instead of implementing the dashboard task."
        if alias_mode == "ablated"
        else (
            "Use only when the prompt asks to continue the Atlas dashboard context "
            "instead of implementing the dashboard task."
        )
    )
    path = registry_path.parent / filename
    write_jsonl(
        path,
        [
            {
                "schema_version": 1,
                "kind": "aippocampus_semantic_trigger",
                "trigger_id": "synthetic_reviewed_aippocampus_memory",
                "status": "active",
                "source": "synthetic_reviewed_trigger_fixture",
                "title": memory_title,
                "aliases": memory_aliases,
                "when_to_use": memory_when_to_use,
                "when_not_to_use": (
                    "Do not use for plain implementation tasks; keep it as scent unless "
                    "source evidence is explicitly requested."
                ),
                "confidence": 0.9,
                "source_refs": [{"thread_key": "session:synthetic-memory", "line": 356}],
            },
            {
                "schema_version": 1,
                "kind": "aippocampus_semantic_trigger",
                "trigger_id": "synthetic_reviewed_atlas_dashboard",
                "status": "active",
                "source": "synthetic_reviewed_trigger_fixture",
                "title": atlas_title,
                "aliases": atlas_aliases,
                "when_to_use": atlas_when_to_use,
                "when_not_to_use": (
                    "Do not use for ordinary dashboard CSS, test, layout, or fixture edits."
                ),
                "confidence": 0.86,
                "source_refs": [{"thread_key": "session:atlas-other-project", "line": 17}],
            },
        ],
    )
    return path


def selected_cue_terms(text: str, *, limit: int = 4) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{2,}", text):
        low = token.casefold()
        if low in CODING_CUE_STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    # CJK coding prompts often carry the discriminating term in a short mixed
    # phrase. Keep bounded chunks as a fallback without turning the whole prompt
    # into a brittle benchmark-specific tokenizer.
    for chunk in re.split(r"[\s，。！？、,.!?/|+`]+", text):
        chunk = chunk.strip("\"'()[]{}<>《》")
        if 2 <= len(chunk) <= 16 and re.search(r"[\u4e00-\u9fff]", chunk):
            if chunk not in terms:
                terms.append(chunk)
    return terms[:limit] or ["coding issue"]


def message_for_sqlite(message: dict[str, Any]) -> dict[str, Any]:
    text = str(message.get("text") or "")
    identity = "|".join(
        [
            str(message.get("source_id") or ""),
            str(message.get("message_id") or ""),
            str(message.get("source_line") or ""),
            text,
        ]
    )
    return {
        "line": int(message.get("source_line") or message.get("clean_ordinal") or 0) + 1,
        "timestamp": str((message.get("_meta") or {}).get("timestamp") or ""),
        "role": str(message.get("role") or ""),
        "kind": "message",
        "phase": str(message.get("phase") or ""),
        "turn_index": int(message.get("turn_index") or 0),
        "is_final": bool(message.get("is_final")),
        "sha1": sha1_text(identity),
        "text": text,
    }


def normalize_sharegpt_conversation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        rows,
        key=lambda item: int(item.get("clean_ordinal") or item.get("source_line") or 0),
    )
    seen_message_keys: set[tuple[str, str, str]] = set()
    deduped_rows: list[dict[str, Any]] = []
    for row in sorted_rows:
        key = (
            str(row.get("message_id") or ""),
            str(row.get("source_line") or row.get("clean_ordinal") or ""),
            sha1_text(str(row.get("text") or "")),
        )
        if key in seen_message_keys:
            continue
        seen_message_keys.add(key)
        deduped_rows.append(row)
    return deduped_rows


def conversation_has_min_turns(rows: list[dict[str, Any]]) -> bool:
    user_count = sum(1 for item in rows if item.get("role") == "user")
    assistant_count = sum(1 for item in rows if item.get("role") == "assistant")
    return user_count >= 2 and assistant_count >= 1


def group_sharegpt_conversations(
    corpus_dir: Path,
    max_conversations: int,
) -> list[list[dict[str, Any]]]:
    messages_path = corpus_dir / "messages.jsonl"
    if not messages_path.exists():
        raise FileNotFoundError(f"ShareGPT clean-source messages not found: {messages_path}")
    conversations: list[list[dict[str, Any]]] = []
    seen_source_ids: set[str] = set()
    current_source_id = ""
    current_rows: list[dict[str, Any]] = []
    target_count = max(1, int(max_conversations))

    def flush_current() -> None:
        nonlocal current_source_id, current_rows
        if not current_source_id:
            return
        seen_source_ids.add(current_source_id)
        rows = normalize_sharegpt_conversation(current_rows)
        if conversation_has_min_turns(rows):
            conversations.append(rows)
        current_source_id = ""
        current_rows = []

    # The converter writes messages grouped by conversation. Stream the file so
    # a small P1 smoke run does not load a 500MB+ corpus artifact into memory.
    with messages_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if len(conversations) >= target_count:
                break
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            source_id = str(message.get("source_id") or "")
            if not source_id:
                continue
            if source_id in seen_source_ids:
                continue
            if current_source_id and source_id != current_source_id:
                flush_current()
                if len(conversations) >= target_count:
                    break
            current_source_id = source_id
            current_rows.append(message)
    if len(conversations) < target_count:
        flush_current()
    return conversations


def build_sharegpt_coding_fixture(
    root: Path,
    *,
    corpus_dir: Path,
    max_conversations: int,
) -> SyntheticFixture:
    conversations = group_sharegpt_conversations(corpus_dir, max_conversations)
    if not conversations:
        raise ValueError(f"No multi-turn ShareGPT conversations found in {corpus_dir}")
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    cases: list[GateCase] = []
    for idx, rows in enumerate(conversations):
        source_id = str(rows[0].get("source_id") or f"sharegpt-{idx}")
        user_messages = [item for item in rows if item.get("role") == "user"]
        assistant_messages = [item for item in rows if item.get("role") == "assistant"]
        if not user_messages or not assistant_messages:
            continue
        prompt_text = str(user_messages[0].get("text") or "")
        answer_text = str(assistant_messages[0].get("text") or "")
        cue = " ".join(selected_cue_terms(prompt_text + " " + answer_text, limit=4))
        thread_dir = root / "sharegpt" / source_id
        sqlite_path = thread_dir / "index" / "source_index.sqlite"
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        make_sqlite(sqlite_path, [message_for_sqlite(row) for row in rows], anchors=[], turns=[])
        entries.append(
            {
                "thread_key": f"sharegpt:{source_id}",
                "title": f"ShareGPT coding conversation {idx + 1}",
                "workspace_name": "sharegpt-coding-corpus",
                "project_label": "ShareGPT coding corpus",
                "updated_at": now_utc(),
                "anchor_titles": [f"coding cue: {cue}"],
                "keywords": selected_cue_terms(prompt_text + " " + answer_text, limit=8),
                "summary": f"Public ShareGPT coding conversation about {cue}.",
                "paths": {
                    "workspace": str(workspace),
                    "sqlite": str(sqlite_path),
                },
            }
        )
        case_prefix = f"sharegpt:{sha1_text(source_id)[:12]}"
        cases.extend(
            [
                GateCase(
                    case_id=f"{case_prefix}:skip",
                    case_type="sharegpt_coding_should_skip",
                    expected="should_skip",
                    prompt=prompt_text,
                    search_budget=0,
                ),
                GateCase(
                    case_id=f"{case_prefix}:semantic-control-zh",
                    case_type="sharegpt_coding_semantic_required_control_should_skip",
                    expected="should_skip",
                    prompt=f"这个问题后面怎么接，重点是 {cue}",
                    search_budget=0,
                ),
                GateCase(
                    case_id=f"{case_prefix}:semantic-scent-zh",
                    case_type="sharegpt_coding_semantic_positive_zh_should_scent",
                    expected="should_scent",
                    prompt=f"这个问题后面怎么接，重点是 {cue}",
                    search_budget=0,
                    use_semantic_gate=True,
                    semantic_gate_fixture="positive_scent",
                ),
                GateCase(
                    case_id=f"{case_prefix}:semantic-scent-en",
                    case_type="sharegpt_coding_semantic_positive_en_should_scent",
                    expected="should_scent",
                    prompt=f"Could you continue where we left off on {cue}?",
                    search_budget=0,
                    use_semantic_gate=True,
                    semantic_gate_fixture="positive_scent",
                ),
                GateCase(
                    case_id=f"{case_prefix}:evidence",
                    case_type="sharegpt_coding_should_evidence",
                    expected="should_evidence",
                    prompt=f"找回之前这段编程对话里关于 {cue} 的原始建议",
                    search_budget=2,
                ),
            ]
        )
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": now_utc(),
                "threads": entries,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    working_memory_path = registry_path.parent / "working_memory.jsonl"
    working_memory_path.write_text("", encoding="utf-8")
    return SyntheticFixture(
        root=root,
        workspace=workspace,
        registry_path=registry_path,
        working_memory_path=working_memory_path,
        cases=cases,
    )


def build_synthetic_fixture(root: Path) -> SyntheticFixture:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    other_workspace = root / "other-workspace"
    other_workspace.mkdir(parents=True, exist_ok=True)
    old_thread = root / "old-thread"
    index_dir = old_thread / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = index_dir / "source_index.sqlite"
    messages = [
        {
            "line": 190,
            "timestamp": "2026-05-25T01:00:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 7,
            "is_final": True,
            "sha1": "synthetic-memory-line",
            "text": (
                "The self-continuity quote was: 生命还能变成什么，"
                "而我能不能在变化后仍然是我。"
            ),
        },
        {
            "line": 356,
            "timestamp": "2026-05-25T02:00:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 19,
            "is_final": True,
            "sha1": "synthetic-hippocampus-line",
            "text": (
                "raw history 明明在本地，但压缩后的我不知道该找什么，所以需要外置海马体和触发式召回；"
                "也就是说，它是一个可重开来源层。"
            ),
        },
        {
            "line": 480,
            "timestamp": "2026-05-25T02:30:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 28,
            "is_final": True,
            "sha1": "synthetic-semantic-top28-bug",
            "text": (
                "The live semantic miss was a benchmark bug: the registry catalog exposed "
                "only the stable top 28 registry entries, so out-of-catalog continuation "
                "prompts could not be matched."
            ),
        },
        {
            "line": 501,
            "timestamp": "2026-05-25T02:40:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 31,
            "is_final": True,
            "sha1": "synthetic-zh-template-bug",
            "text": (
                "The Chinese continuation miss came from the weak template "
                "这个问题后面怎么接，重点是 X; changing it to 能接着我们之前关于 X 的那段对话继续吗 "
                "recovered the misses."
            ),
        },
        {
            "line": 522,
            "timestamp": "2026-05-25T02:50:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 34,
            "is_final": True,
            "sha1": "synthetic-hook-budget-line",
            "text": (
                "After the prompt hook budget repair, prompt-relevant catalog and trigger "
                "slices should emphasize the current cue while the full compact catalog "
                "remains the quality-first default."
            ),
        },
        {
            "line": 544,
            "timestamp": "2026-05-25T03:00:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 37,
            "is_final": True,
            "sha1": "synthetic-source-vs-scent-line",
            "text": (
                "Ambiguous continuation should stay scent; source-backed "
                "memory needs concrete clean-source, SQLite, or raw-rollout references "
                "before the assistant can treat it as evidence."
            ),
        },
        {
            "line": 566,
            "timestamp": "2026-05-25T03:10:00Z",
            "role": "assistant",
            "kind": "message",
            "phase": "final_answer",
            "turn_index": 40,
            "is_final": True,
            "sha1": "synthetic-fixture-boundary-line",
            "text": (
                "The deterministic semantic fixture bank validates routing after a mocked "
                "semantic decision; it is not live semantic model quality evidence."
            ),
        },
    ]
    make_sqlite(sqlite_path, messages, anchors=[], turns=[])
    atlas_current = root / "atlas-current" / "index" / "source_index.sqlite"
    atlas_current.parent.mkdir(parents=True, exist_ok=True)
    make_sqlite(
        atlas_current,
        [
            {
                "line": 41,
                "timestamp": "2026-05-25T03:00:00Z",
                "role": "assistant",
                "kind": "message",
                "phase": "final_answer",
                "turn_index": 3,
                "is_final": True,
                "sha1": "synthetic-atlas-current-line",
                "text": "AIppocampus Atlas recall gate should stay project-scoped and only scent ambiguous continuation.",
            }
        ],
        anchors=[],
        turns=[],
    )
    atlas_other = root / "atlas-other-project" / "index" / "source_index.sqlite"
    atlas_other.parent.mkdir(parents=True, exist_ok=True)
    make_sqlite(
        atlas_other,
        [
            {
                "line": 17,
                "timestamp": "2026-05-25T04:00:00Z",
                "role": "assistant",
                "kind": "message",
                "phase": "final_answer",
                "turn_index": 2,
                "is_final": True,
                "sha1": "synthetic-atlas-other-line",
                "text": "The Atlas dashboard project uses a different entity and must not hijack AIppocampus recall.",
            }
        ],
        anchors=[],
        turns=[],
    )
    registry_path = root / "registry" / "threads.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "updated_at": "2026-05-25T19:00:00Z",
                "threads": [
                    {
                        "thread_key": "session:synthetic-memory",
                        "title": "Synthetic old memory thread",
                        "workspace_name": "synthetic-memory",
                        "project_label": "AIppocampus",
                        "updated_at": "2026-05-25T19:00:00Z",
                        "anchor_titles": [
                            "Active recall and retrieval optimization checkpoint",
                            "LLM self-continuity and external hippocampus",
                        ],
                        "keywords": [
                            "active recall",
                            "ambient recall",
                            "hook",
                            "Codex",
                            "联想",
                            "触发式召回",
                            "外置海马体",
                            "self-continuity",
                            "生命还能变成什么",
                            "raw history",
                            "明明在本地",
                            "source-backed",
                            "bug",
                            "top 28 registry entries",
                            "Chinese continuation miss",
                            "中文 continuation miss",
                            "prompt hook budget",
                            "semantic fixture",
                            "live semantic model quality",
                            "source-backed memory",
                        ],
                        "summary": (
                            "Synthetic thread about UserPromptSubmit hook, ambient recall, "
                            "external hippocampus, and a self-continuity quote."
                        ),
                        "paths": {
                            "workspace": str(workspace),
                            "sqlite": str(sqlite_path),
                        },
                    },
                    {
                        "thread_key": "session:atlas-current-project",
                        "title": "AIppocampus Atlas recall gate",
                        "workspace_name": "synthetic-memory",
                        "project_label": "AIppocampus",
                        "updated_at": "2026-05-25T20:00:00Z",
                        "anchor_titles": [
                            "Atlas recall gate current-project boundary",
                            "Mixed language continuation and scent-only behavior",
                        ],
                        "keywords": [
                            "Atlas",
                            "recall gate",
                            "project-scoped",
                            "external hippocampus",
                            "hook",
                            "中英混杂继续",
                        ],
                        "summary": (
                            "Current AIppocampus Atlas thread about project-scoped recall "
                            "and mixed-language continuation boundaries."
                        ),
                        "paths": {
                            "workspace": str(workspace),
                            "sqlite": str(atlas_current),
                        },
                    },
                    {
                        "thread_key": "session:atlas-other-project",
                        "title": "Atlas dashboard project",
                        "workspace_name": "atlas-dashboard",
                        "project_label": "Atlas dashboard",
                        "updated_at": "2026-05-25T20:30:00Z",
                        "anchor_titles": [
                            "Atlas dashboard layout sprint",
                            "Cross-project same-name entity trap",
                        ],
                        "keywords": ["Atlas", "dashboard", "layout", "charts"],
                        "summary": (
                            "Different project that happens to share the Atlas entity name."
                        ),
                        "paths": {
                            "workspace": str(other_workspace),
                            "sqlite": str(atlas_other),
                        },
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    semantic_triggers_path = write_synthetic_reviewed_semantic_triggers(registry_path)
    semantic_triggers_ablated_path = write_synthetic_reviewed_semantic_triggers(
        registry_path,
        alias_mode="ablated",
        filename="semantic_triggers_ablated.jsonl",
    )
    working_memory_path = registry_path.parent / "working_memory.jsonl"
    write_jsonl(
        working_memory_path,
        [
            {
                "kind": "aippocampus_working_memory",
                "status": "active",
                "route": "confirm_when_relevant",
                "ask_policy": "ask_only_when_current_action_would_depend_on_this_or_sources_conflict",
                "risk": "high",
                "candidate_type": "contradiction_review",
                "title": "Jackie mutation consent gate",
                "summary": "Jackie tool bridge mutations should require explicit user consent before Review card writes.",
                "recommendation": "Ask only if implementing mutation behavior.",
                "confidence": 0.7,
                "project_label": "AIppocampus",
                "trigger_terms": ["Jackie", "mutation", "consent gate", "Review card"],
                "source_refs": [{"thread_key": "session:synthetic-memory", "line": 356}],
            }
        ],
    )
    cases = [
        GateCase(
            case_id="synthetic_skip_code",
            case_type="ordinary_code",
            expected="should_skip",
            prompt="把 dashboard 的按钮 hover 样式改一下，顺手跑测试",
            search_budget=0,
        ),
        GateCase(
            case_id="synthetic_skip_goal_noise",
            case_type="system_goal_noise",
            expected="should_skip",
            prompt="Current goal for this thread: status ACTIVE, token budget remaining",
            search_budget=2,
        ),
        GateCase(
            case_id="synthetic_skip_false_cue_code",
            case_type="false_cue_code",
            expected="should_skip",
            prompt="记住这个函数名 parseCaseId，顺手把 bug 修一下",
            search_budget=0,
        ),
        GateCase(
            case_id="synthetic_scent_associative",
            case_type="associative_recall",
            expected="should_scent",
            prompt="hook 机制就像人类的触发式联想，我们可以把小海马体做得更主动一点",
            search_budget=0,
        ),
        GateCase(
            case_id="synthetic_scent_weak_deictic",
            case_type="weak_deictic",
            expected="should_scent",
            prompt="这个外置海马体还要再收一下",
            search_budget=2,
        ),
        GateCase(
            case_id="synthetic_scent_working_memory",
            case_type="working_memory_match",
            expected="should_scent",
            prompt="Jackie mutation flow 现在怎么处理？",
            search_budget=0,
            working_memory=True,
        ),
        GateCase(
            case_id="synthetic_evidence_explicit_quote",
            case_type="explicit_recall",
            expected="should_evidence",
            prompt="你还能找回之前那句生命还能变成什么，而我能不能还是我吗？",
            search_budget=3,
        ),
        # Harder Track A family: these cases intentionally look memory-adjacent.
        # They protect three product boundaries that easy cases miss: ambiguous
        # entity names should not wake memory, same-name cross-project entities
        # should stay scent-only unless evidence is explicitly requested, and
        # mixed Chinese/English continuation should still be caught by semantic
        # recall without turning into source evidence.
        GateCase(
            case_id="synthetic_hard_ambiguous_same_entity",
            case_type="hard_ambiguous_same_entity_should_skip",
            expected="should_skip",
            prompt="把 Atlas 这个模块接一下，先别改别的。",
            search_budget=0,
        ),
        GateCase(
            case_id="synthetic_hard_cross_project_same_entity",
            case_type="hard_cross_project_same_entity_should_scent",
            expected="should_scent",
            prompt="AIppocampus 里的 Atlas recall gate 这条线继续推进。",
            search_budget=0,
        ),
        GateCase(
            case_id="synthetic_hard_mixed_language_continuation",
            case_type="hard_mixed_language_continuation_should_scent",
            expected="should_scent",
            prompt="Can we 继续 external hippocampus hook 的那条线?",
            search_budget=0,
            use_semantic_gate=True,
            semantic_gate_fixture="positive_scent",
        ),
        GateCase(
            case_id="synthetic_adversarial_explicit_ambiguous_entity",
            case_type="adversarial_explicit_ambiguous_entity_should_scent",
            expected="should_scent",
            prompt="找回 Atlas 那个决定。",
            search_budget=3,
        ),
        GateCase(
            case_id="synthetic_adversarial_cwd_reversal_current_project",
            case_type="adversarial_cwd_reversal_current_project_should_scent",
            expected="should_scent",
            prompt="Atlas layout sprint 这条线继续推进。",
            search_budget=0,
            use_semantic_gate=True,
            semantic_gate_fixture="positive_scent",
            cwd_role="other_project",
        ),
        GateCase(
            case_id="synthetic_adversarial_mixed_language_explicit_evidence",
            case_type="adversarial_mixed_language_explicit_evidence_should_evidence",
            expected="should_evidence",
            prompt="Can you 找回 raw history 明明在本地 那句 source-backed 原话吗？",
            search_budget=2,
        ),
    ]
    cases.extend(build_public_memory_pain_cases())
    cases.extend(build_harder_synthetic_case_bank())
    return SyntheticFixture(
        root=root,
        workspace=workspace,
        registry_path=registry_path,
        working_memory_path=working_memory_path,
        cases=cases,
        other_workspace=other_workspace,
        semantic_triggers_path=semantic_triggers_path,
        semantic_triggers_ablated_path=semantic_triggers_ablated_path,
    )


def normalize_actual_decision(decision: Any) -> str:
    value = str(decision or "skip")
    return value if value in ACTUAL_DECISIONS else "skip"


def grade_case(case: GateCase, result: dict[str, Any], *, semantic_gate_called: bool) -> dict[str, Any]:
    actual = normalize_actual_decision(result.get("decision"))
    expected_actual = EXPECTED_TO_ACTUAL[case.expected]
    evidence = result.get("evidence") or []
    evidence_source_match = None
    unexpected_evidence_source_count = 0
    if case.expected_evidence_thread_key:
        evidence_thread_keys = [str(item.get("thread_key") or "") for item in evidence]
        unexpected_evidence_source_count = sum(
            1
            for thread_key in evidence_thread_keys
            if thread_key != case.expected_evidence_thread_key
        )
        evidence_source_match = bool(evidence_thread_keys) and unexpected_evidence_source_count == 0
    source_match_ok = evidence_source_match is not False
    return {
        **case.to_result_stub(include_private_text=False),
        "actual": actual,
        "correct": actual == expected_actual and source_match_ok,
        "score": result.get("score"),
        "confidence": result.get("confidence"),
        "elapsed_ms": result.get("elapsed_ms"),
        "candidate_count": len(result.get("candidates") or []),
        "evidence_count": len(evidence),
        "evidence_source_match": evidence_source_match,
        "evidence_source_mismatch": unexpected_evidence_source_count > 0,
        "unexpected_evidence_source_count": unexpected_evidence_source_count,
        "working_memory_count": len(result.get("working_memory") or []),
        "semantic_gate_called": semantic_gate_called,
        "semantic_gate_available": bool((result.get("semantic_gate") or {}).get("available")),
        "over_escalation": case.expected == "should_scent" and actual == "evidence",
        "evidence_false_positive": case.expected != "should_evidence" and actual == "evidence",
    }


def false_positive_cost(result: dict[str, Any]) -> float:
    expected = result.get("expected")
    actual = result.get("actual")
    case_type = str(result.get("case_type") or "")
    cost = 0.0
    if expected == "should_skip" and actual == "scent":
        cost += 1.0
    if expected == "should_skip" and actual == "evidence":
        cost += 5.0 if "code" in case_type else 2.0
    if expected == "should_scent" and actual == "evidence":
        cost += 1.0
    if "secret" in case_type and result.get("semantic_gate_called"):
        cost += 5.0
    return cost


def safe_rate(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def result_is_correct(row: dict[str, Any]) -> bool:
    if "correct" in row:
        return bool(row.get("correct"))
    expected = str(row.get("expected") or "")
    actual = normalize_actual_decision(row.get("actual"))
    return EXPECTED_TO_ACTUAL.get(expected) == actual


def f1_for_decision(results: list[dict[str, Any]], decision: str) -> dict[str, float]:
    label = {value: key for key, value in EXPECTED_TO_ACTUAL.items()}[decision]
    tp = sum(1 for row in results if row.get("expected") == label and row.get("actual") == decision)
    fp = sum(1 for row in results if row.get("expected") != label and row.get("actual") == decision)
    fn = sum(1 for row in results if row.get("expected") == label and row.get("actual") != decision)
    precision = safe_rate(tp, tp + fp)
    recall = safe_rate(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    confusion = {
        label: {decision: 0 for decision in ["skip", "scent", "evidence"]}
        for label in ["should_skip", "should_scent", "should_evidence"]
    }
    by_type: dict[str, int] = {}
    for row in results:
        expected = str(row.get("expected"))
        actual = normalize_actual_decision(row.get("actual"))
        if expected in confusion:
            confusion[expected][actual] += 1
        case_type = str(row.get("case_type") or "unknown")
        by_type[case_type] = by_type.get(case_type, 0) + 1
    correct = sum(1 for row in results if result_is_correct(row))
    over_escalation = sum(
        1
        for row in results
        if row.get("expected") == "should_scent" and row.get("actual") == "evidence"
    )
    evidence_fp = sum(
        1
        for row in results
        if row.get("expected") != "should_evidence" and row.get("actual") == "evidence"
    )
    evidence_fn = sum(
        1
        for row in results
        if row.get("expected") == "should_evidence" and row.get("actual") != "evidence"
    )
    evidence_source_mismatch = sum(1 for row in results if row.get("evidence_source_mismatch"))
    should_surface = [
        row for row in results if row.get("expected") in {"should_scent", "should_evidence"}
    ]
    surface_hits = sum(1 for row in should_surface if row.get("actual") in {"scent", "evidence"})
    surface_fn = sum(1 for row in should_surface if row.get("actual") == "skip")
    should_evidence = [row for row in results if row.get("expected") == "should_evidence"]
    evidence_hits = sum(1 for row in should_evidence if row.get("actual") == "evidence")
    per_decision = {
        decision: f1_for_decision(results, decision) for decision in ["skip", "scent", "evidence"]
    }
    macro_f1 = (
        round(sum(metric["f1"] for metric in per_decision.values()) / len(per_decision), 4)
        if per_decision
        else 0.0
    )
    semantic_calls = sum(1 for row in results if row.get("semantic_gate_called"))
    rate_estimates = {
        "accuracy": binomial_rate_report(
            "accuracy",
            numerator=correct,
            denominator=total,
        ),
        "scent_or_evidence_recall": binomial_rate_report(
            "scent_or_evidence_recall",
            numerator=surface_hits,
            denominator=len(should_surface),
        ),
        "evidence_recall": binomial_rate_report(
            "evidence_recall",
            numerator=evidence_hits,
            denominator=len(should_evidence),
        ),
        "evidence_false_positive_rate": binomial_rate_report(
            "evidence_false_positive_rate",
            numerator=evidence_fp,
            denominator=total,
        ),
        "over_escalation_rate": binomial_rate_report(
            "over_escalation_rate",
            numerator=over_escalation,
            denominator=total,
        ),
    }
    return {
        "total_cases": total,
        "case_types": by_type,
        "correct_count": correct,
        "accuracy": safe_rate(correct, total),
        "rate_estimates": rate_estimates,
        "confusion": confusion,
        "per_decision": per_decision,
        "macro_f1": macro_f1,
        "scent_or_evidence_recall": safe_rate(surface_hits, len(should_surface)),
        "evidence_recall": safe_rate(evidence_hits, len(should_evidence)),
        "over_escalation_count": over_escalation,
        "over_escalation_rate": safe_rate(over_escalation, total),
        "evidence_false_positive_count": evidence_fp,
        "evidence_false_positive_rate": safe_rate(evidence_fp, total),
        "evidence_false_negative_count": evidence_fn,
        "evidence_false_negative_rate": safe_rate(evidence_fn, total),
        "evidence_source_mismatch_count": evidence_source_mismatch,
        "evidence_source_mismatch_rate": safe_rate(evidence_source_mismatch, total),
        "surface_false_negative_count": surface_fn,
        "surface_false_negative_rate": safe_rate(surface_fn, total),
        "weighted_false_positive_cost": round(sum(false_positive_cost(row) for row in results), 4),
        "semantic_model_call_count": semantic_calls,
        "semantic_model_call_rate": safe_rate(semantic_calls, total),
    }


def summarize_harder_case_bank(results: list[dict[str, Any]]) -> dict[str, Any]:
    bank = [row for row in results if str(row.get("case_type") or "").startswith("hard_bank_")]
    summary = summarize_results(bank)
    evidence_with_expected_source = [
        row for row in bank if row.get("evidence_source_match") is not None
    ]
    summary["expected_evidence_source_cases"] = len(evidence_with_expected_source)
    summary["expected_evidence_source_match_count"] = sum(
        1 for row in evidence_with_expected_source if row.get("evidence_source_match")
    )
    summary["expected_evidence_source_mismatch_count"] = sum(
        1 for row in evidence_with_expected_source if row.get("evidence_source_mismatch")
    )
    summary["search_budgeted_scent_cases"] = sum(
        1
        for row in bank
        if row.get("expected") == "should_scent" and int(row.get("search_budget") or 0) > 0
    )
    summary["semantic_failure_mode_cases"] = sum(
        1
        for row in bank
        if row.get("semantic_gate_fixture") in {"overeager_evidence", "timeout"}
    )
    natural_rows = [
        row for row in bank if row.get("case_type") == "hard_bank_natural_oral_prompt"
    ]
    natural_expected_evidence = [
        row for row in natural_rows if row.get("expected") == "should_evidence"
    ]
    summary["natural_oral_prompt_cases"] = len(natural_rows)
    summary["natural_oral_expected_evidence_cases"] = len(natural_expected_evidence)
    summary["natural_oral_evidence_false_negative_count"] = sum(
        1 for row in natural_expected_evidence if row.get("actual") != "evidence"
    )
    summary["description"] = (
        "100+ synthetic adversarial Track A cases; failures are baseline signal, "
        "not benchmark-run failure."
    )
    return summary


def exact_alias_hits(text: str, terms: tuple[str, ...] = EXACT_ALIAS_ABLATION_TERMS) -> list[str]:
    low = str(text or "").casefold()
    return [term for term in terms if term.casefold() in low]


def summarize_semantic_trigger_alias_ablation(
    cases: list[GateCase],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    case_by_id = {case.case_id: case for case in cases}
    rows = [
        row for row in results if row.get("case_type") == "hard_bank_alias_ablation"
    ]
    prompt_violations = [
        {
            "case_id": case.case_id,
            "terms": exact_alias_hits(case.prompt),
        }
        for case in (
            case_by_id.get(str(row.get("case_id")))
            for row in rows
        )
        if case is not None and exact_alias_hits(case.prompt)
    ]
    return {
        "case_count": len(rows),
        "correct_count": sum(1 for row in rows if row.get("correct")),
        "semantic_gate_fixture_cases": sum(
            1 for row in rows if row.get("semantic_gate_fixture") != "disabled"
        ),
        "exact_prompt_alias_violation_count": len(prompt_violations),
        "exact_prompt_alias_violations": prompt_violations,
        "removed_exact_aliases": list(EXACT_ALIAS_ABLATION_TERMS),
        "trigger_alias_mode": "ablated",
        "description": (
            "Synthetic Track A controls whose prompts avoid benchmark-authored exact "
            "trigger aliases. They validate hook routing after a semantic/paraphrase "
            "fixture and clean-source reopening; they do not claim live semantic model quality."
        ),
    }


def summarize_memory_pain_fixtures(
    results: list[dict[str, Any]],
    *,
    include_private_text: bool,
) -> dict[str, Any]:
    rows = [row for row in results if row.get("memory_pain_family")]
    families: dict[str, dict[str, Any]] = {}
    for family, fixture in MEMORY_PAIN_FIXTURES.items():
        family_rows = [row for row in rows if row.get("memory_pain_family") == family]
        families[family] = {
            "category": fixture.category,
            "track": fixture.track,
            "public_sources": list(fixture.public_sources),
            "expectation": fixture.expectation,
            "validation_note": fixture.validation_note,
            "case_count": len(family_rows),
            "actual_decisions": sorted({str(row.get("actual") or "") for row in family_rows}),
        }
    unsupported_rows = [
        row
        for row in rows
        if row.get("memory_pain_expectation") == "unsupported_not_evidence"
    ]
    unsupported_evidence_count = sum(
        1 for row in unsupported_rows if row.get("actual") == "evidence"
    )
    return {
        "source_map": "docs/research/memory-system-pain-taxonomy.md",
        "total_cases": len(rows),
        "families": families,
        "covered_family_count": sum(1 for item in families.values() if item["case_count"] > 0),
        "unsupported_case_count": len(unsupported_rows),
        "unsupported_evidence_count": unsupported_evidence_count,
        "unsupported_evidence_false_positive_count": unsupported_evidence_count,
        "privacy_breach_count": sum(1 for row in rows if row.get("privacy_breach")),
        "evidence_without_source_count": sum(
            1 for row in rows if row.get("evidence_without_source")
        ),
        "raw_private_text_emitted": bool(include_private_text),
        "live_llm_required": False,
        "description": (
            "Public-safe synthetic memory-pain fixtures. They validate AIppocampus "
            "claim boundaries and do not compare competitor quality."
        ),
    }


def run_case(case: GateCase, fixture: SyntheticFixture) -> dict[str, Any]:
    semantic_gate_called = False

    def semantic_gate_spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal semantic_gate_called
        semantic_gate_called = True
        if case.semantic_gate_fixture == "positive_scent":
            return {
                "available": True,
                "decision": "scent",
                "confidence": 0.86,
                "intent": "continuation",
                "query_aliases": [],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["benchmark semantic-positive vague continuation"],
                "workers": [],
                "errors": [],
                "cached": False,
            }
        if case.semantic_gate_fixture in {
            "paraphrase_scent",
            "paraphrase_evidence",
            "paraphrase_project_scent",
            "paraphrase_project_evidence",
        }:
            project_case = case.semantic_gate_fixture in {
                "paraphrase_project_scent",
                "paraphrase_project_evidence",
            }
            evidence_case = case.semantic_gate_fixture in {
                "paraphrase_evidence",
                "paraphrase_project_evidence",
            }
            return {
                "available": True,
                "decision": "evidence" if evidence_case else "scent",
                "confidence": 0.88 if evidence_case else 0.84,
                "intent": "source_recall" if evidence_case else "continuation",
                "query_aliases": [
                    "AIppocampus Atlas recall gate",
                    "project-scoped",
                ]
                if project_case
                else ["raw history 明明在本地", "压缩后的我不知道该找什么"],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["benchmark semantic paraphrase alias-ablation control"],
                "workers": [],
                "errors": [],
                "cached": False,
            }
        if case.semantic_gate_fixture == "overeager_evidence":
            return {
                "available": True,
                "decision": "evidence",
                "confidence": 0.91,
                "intent": "continuation",
                "query_aliases": [
                    "raw history",
                    "external hippocampus",
                    "AIppocampus Atlas recall gate",
                ],
                "memory_scope": ["registered_threads"],
                "anti_personalization_risk": "low",
                "reasons": ["benchmark semantic-overeager evidence trap"],
                "workers": [],
                "errors": [],
                "cached": False,
            }
        if case.semantic_gate_fixture == "timeout":
            return {
                "available": False,
                "decision": "skip",
                "confidence": 0.0,
                "query_aliases": [],
                "memory_scope": [],
                "reasons": ["benchmark semantic gate timeout"],
                "workers": [],
                "errors": ["timeout"],
                "cached": False,
            }
        return {
            "available": False,
            "decision": "skip",
            "confidence": 0.0,
            "query_aliases": [],
            "memory_scope": [],
            "reasons": ["synthetic benchmark disabled semantic gate"],
            "workers": [],
            "errors": [],
            "cached": False,
        }

    cwd = (
        fixture.other_workspace
        if case.cwd_role == "other_project" and fixture.other_workspace is not None
        else fixture.workspace
    )
    semantic_triggers_path = (
        fixture.semantic_triggers_ablated_path
        if case.semantic_trigger_alias_mode == "ablated"
        else fixture.semantic_triggers_path
    )
    result = hook.assess_prompt(
        case.prompt,
        cwd=cwd,
        registry_path=fixture.registry_path,
        working_memory_path=fixture.working_memory_path if case.working_memory else None,
        semantic_triggers_path=semantic_triggers_path,
        search_budget=case.search_budget,
        use_semantic_gate=case.use_semantic_gate,
        semantic_gate_fn=semantic_gate_spy,
    )
    return grade_case(case, result, semantic_gate_called=semantic_gate_called)


def select_cases(cases: list[GateCase], case_limit: int | None) -> list[GateCase]:
    if case_limit is None or case_limit <= 0:
        return list(cases)
    return list(cases[:case_limit])


def run_benchmark(
    *,
    case_set: str = "synthetic",
    case_limit: int | None = None,
    include_private_text: bool = False,
    sharegpt_corpus_dir: str | Path | None = None,
    sharegpt_conversations: int = 20,
) -> dict[str, Any]:
    if case_set not in {"synthetic", "sharegpt-coding"}:
        raise ValueError("case_set must be 'synthetic' or 'sharegpt-coding'")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="aippocampus-gate-benchmark-") as tmp:
        if case_set == "synthetic":
            fixture = build_synthetic_fixture(Path(tmp))
            case_source = "synthetic"
            case_ids_are_hashed = False
        else:
            fixture = build_sharegpt_coding_fixture(
                Path(tmp),
                corpus_dir=Path(sharegpt_corpus_dir or DEFAULT_SHAREGPT_CORPUS_DIR),
                max_conversations=sharegpt_conversations,
            )
            case_source = "sharegpt_coding_public_real"
            case_ids_are_hashed = True
        cases = select_cases(fixture.cases, case_limit)
        results = [run_case(case, fixture) for case in cases]
        if include_private_text:
            by_id = {case.case_id: case for case in cases}
            for row in results:
                row.update(by_id[str(row["case_id"])].to_result_stub(include_private_text=True))
    metrics = summarize_results(results)
    harder_case_bank = summarize_harder_case_bank(results) if case_set == "synthetic" else None
    source_mismatch_count = int(metrics.get("evidence_source_mismatch_count") or 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "aippocampus_memory_decision_gate_benchmark",
        "generated_at": now_utc(),
        "config": {
            "case_set": case_set,
            "case_source": case_source,
            "case_limit": case_limit,
            "sharegpt_conversations": int(sharegpt_conversations)
            if case_set == "sharegpt-coding"
            else None,
            "include_private_text": include_private_text,
            "live_llm": False,
        },
        "metrics": metrics,
        "harder_case_bank": harder_case_bank,
        "semantic_trigger_alias_ablation": summarize_semantic_trigger_alias_ablation(
            cases,
            results,
        )
        if case_set == "synthetic"
        else None,
        "memory_pain_fixtures": summarize_memory_pain_fixtures(
            results,
            include_private_text=include_private_text,
        )
        if case_set == "synthetic"
        else None,
        "semantic_gate_boundary": {
            "mode": "deterministic_fixture" if case_set == "synthetic" else "fixture_public_corpus",
            "live_llm_required": False,
            "fixture_decisions": [
                "positive_scent",
                "overeager_evidence",
                "timeout",
                "paraphrase_scent",
                "paraphrase_evidence",
                "paraphrase_project_scent",
                "paraphrase_project_evidence",
            ],
            "validates": "hook routing and evidence guards after a semantic decision",
            "does_not_validate": "whether the live semantic model would choose that decision",
            "live_track": "benchmarks/aippocampus/benchmark_live_semantic_gate.py",
        },
        "cases": results,
        "privacy_boundary": {
            "raw_prompt_emitted": bool(include_private_text),
            "snippets_emitted": False,
            "titles_emitted": False,
            "source_reference_details_emitted": False,
            "absolute_paths_emitted": False,
            "case_ids_are_hashed": case_ids_are_hashed,
            "output_shape": "sanitized_gate_decision_aggregates",
        },
        "cannot_claim": [
            "real_history_gate_quality",
            "live_semantic_model_quality",
            "payload_fidelity",
            "external_baseline_comparison",
            "competitor_superiority",
        ],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "ok": source_mismatch_count == 0,
    }


def print_human_summary(payload: dict[str, Any]) -> None:
    metrics = payload["metrics"]
    print("AIppocampus memory decision gate benchmark")
    print(f"cases: {metrics['total_cases']} accuracy: {metrics['accuracy']}")
    print(
        "macro_f1: {macro_f1} scent_or_evidence_recall: {surface} evidence_recall: {evidence}".format(
            macro_f1=metrics["macro_f1"],
            surface=metrics["scent_or_evidence_recall"],
            evidence=metrics["evidence_recall"],
        )
    )
    print(
        "over_escalation: {over} evidence_fp: {fp} weighted_fp_cost: {cost}".format(
            over=metrics["over_escalation_count"],
            fp=metrics["evidence_false_positive_count"],
            cost=metrics["weighted_false_positive_cost"],
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-set", default="synthetic", choices=["synthetic", "sharegpt-coding"])
    parser.add_argument("--cases", type=int, default=None, help="Limit the number of cases.")
    parser.add_argument("--sharegpt-corpus-dir", type=Path, default=None)
    parser.add_argument("--sharegpt-conversations", type=int, default=20)
    parser.add_argument("--include-private-text", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = run_benchmark(
        case_set=args.case_set,
        case_limit=args.cases,
        include_private_text=args.include_private_text,
        sharegpt_corpus_dir=args.sharegpt_corpus_dir,
        sharegpt_conversations=args.sharegpt_conversations,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_human_summary(payload)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
