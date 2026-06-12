"""Shared defaults for the Track B source-evidence benchmark."""

from __future__ import annotations

import re
from typing import Any, Callable

import _paths

_paths.ensure_paths()

SCHEMA_VERSION = 1
DEFAULT_FTS5_CASES = 100
DEFAULT_FTS5_MIN_CASES = 50
DEFAULT_SOURCE_MAX_CASES = 100
DEFAULT_SOURCE_MIN_CASES = 50
DEFAULT_SOURCE_MIN_HIT_RATE = 0.85
DEFAULT_SHAREGPT_PUBLIC_CORPUS_DIR = (
    _paths.REPO_ROOT
    / "benchmark_corpus"
    / "output"
    / "sharegpt_all_multiturn"
).resolve()
DEFAULT_SHAREGPT_PUBLIC_CONVERSATIONS = 100
DEFAULT_SHAREGPT_PUBLIC_CASES = 100
DEFAULT_SHAREGPT_PUBLIC_MIN_CASES = 50
DEFAULT_SHAREGPT_PUBLIC_TOP_K = 10
DEFAULT_SHAREGPT_PUBLIC_MIN_MESSAGE_HIT_RATE = 0.85
DEFAULT_SHAREGPT_PUBLIC_MIN_TURN_HIT_RATE = 0.9
DEFAULT_PUBLIC_SEMANTIC_CONVERSATIONS = 40
DEFAULT_PUBLIC_SEMANTIC_MAX_MESSAGES = 80
DEFAULT_PUBLIC_SEMANTIC_MAX_CANDIDATES = 48
DEFAULT_PUBLIC_SEMANTIC_MAX_CASES = 24
DEFAULT_PUBLIC_SEMANTIC_MIN_CASES = 3
DEFAULT_PUBLIC_SEMANTIC_TOP_K = 5
DEFAULT_PUBLIC_SEMANTIC_MIN_HIT_RATE = 0.75
DEFAULT_PUBLIC_SEMANTIC_MIN_CONFIDENCE = 0.45
DEFAULT_PUBLIC_SEMANTIC_TIMEOUT = 60
DEFAULT_PUBLIC_SEMANTIC_MAX_TOKENS = 8192
# The semantic-sidecar min_cases default is a smoke floor. This separate
# evidence-density floor prevents tiny reviewed pilots from being promoted to
# empirical benchmark claims merely because their top-k hits passed.
DEFAULT_PUBLIC_SEMANTIC_MINIMUM_EMPIRICAL_CASE_COUNT = 50
PUBLIC_SEMANTIC_SELECTION_METHOD = (
    "bounded ShareGPT clean-source subset with source-backed semantic sidecar rows"
)
DEFAULT_STANDARD_CORPUS_ROOT = (_paths.REPO_ROOT / "benchmark_corpus").resolve()
DEFAULT_STANDARD_DATASET = "locomo"
DEFAULT_STANDARD_QA_CASES = 100
DEFAULT_STANDARD_QA_MIN_CASES = 20
DEFAULT_STANDARD_QA_TOP_K = 10
DEFAULT_STANDARD_QA_CONTEXT_RADIUS = 5
DEFAULT_STANDARD_QA_MIN_SESSION_HIT_RATE = 0.5
DEFAULT_STANDARD_LINE_RERANKER_MODE = "off"
DEFAULT_STANDARD_LINE_RERANKER_TOP_SESSIONS = 0
DEFAULT_STANDARD_LINE_RERANKER_MAX_CANDIDATES = 96
DEFAULT_STANDARD_LINE_RERANKER_TIMEOUT = 12
DEFAULT_STANDARD_LINE_RERANKER_MAX_TOKENS = 0
DEFAULT_STANDARD_LINE_RERANKER_WORKERS = 0
STANDARD_LINE_RERANKER_MODES = {"off", "custom", "lexical", "structural", "semantic"}
STANDARD_DATASET_PATHS = {
    "locomo": DEFAULT_STANDARD_CORPUS_ROOT / "locomo" / "locomo10.json",
    "longmemeval-v1-oracle": (
        DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "longmemeval_oracle.json"
    ),
    "longmemeval-v1-small": (
        DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "longmemeval_s_cleaned.json"
    ),
    "longmemeval-v1-medium": (
        DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "longmemeval_m_cleaned.json"
    ),
    "longmemeval-v2": DEFAULT_STANDARD_CORPUS_ROOT / "longmemeval" / "v2_questions.jsonl",
}
LineRerankerFn = Callable[..., dict[str, Any]]
PublicSemanticLabelerFn = Callable[..., dict[str, Any]]
PUBLIC_SOURCE_TERM_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "before",
    "could",
    "from",
    "have",
    "help",
    "into",
    "just",
    "like",
    "please",
    "that",
    "this",
    "what",
    "when",
    "where",
    "with",
    "would",
}
STANDARD_QUERY_TERM_STOPWORDS = PUBLIC_SOURCE_TERM_STOPWORDS | {
    "after",
    "before",
    "being",
    "been",
    "could",
    "current",
    "did",
    "does",
    "done",
    "during",
    "first",
    "going",
    "here",
    "into",
    "know",
    "last",
    "many",
    "much",
    "next",
    "onto",
    "previous",
    "should",
    "than",
    "then",
    "there",
    "they",
    "the",
    "those",
    "too",
    "toward",
    "to",
    "were",
    "while",
    "whose",
    "your",
    "yours",
}
CONTINUATION_RE = re.compile(
    r"(?i)\b(continue|where\s+we\s+left\s+off|pick\s+up|go\s+on)\b|继续|接着|续写|从.*继续"
)
TRACK_B_QUERY_ORIGIN_ISSUES = ["#216", "#301", "#355"]
QUERY_ORIGIN_TAXONOMY = {
    "source_derived_exact": {
        "bucket": "source_derived",
        "independent_of_target_source": False,
        "boundary": "Exact or near-exact terms copied from the expected source.",
    },
    "source_derived_sparse": {
        "bucket": "source_derived",
        "independent_of_target_source": False,
        "boundary": "Sparse terms or prompts derived from the target source or its turn.",
    },
    "human_or_fixture_question": {
        "bucket": "non_source_derived",
        "independent_of_target_source": True,
        "boundary": "Question text authored by the dataset or fixture, not extracted from the target source line.",
    },
    "human_or_fixture_paraphrase": {
        "bucket": "non_source_derived",
        "independent_of_target_source": True,
        "boundary": "Independent paraphrase or degraded cue with fixture-reviewed source refs.",
    },
    "cross_language": {
        "bucket": "non_source_derived",
        "independent_of_target_source": True,
        "boundary": "Independent cross-language cue with fixture-reviewed source refs.",
    },
    "degraded_cue": {
        "bucket": "non_source_derived",
        "independent_of_target_source": True,
        "boundary": "Incomplete or vague cue authored outside the target source text.",
    },
    "adversarial_near_miss": {
        "bucket": "non_source_derived",
        "independent_of_target_source": True,
        "boundary": "Hard negative or near-miss cue where wrong-source retrieval is meaningful.",
    },
}
