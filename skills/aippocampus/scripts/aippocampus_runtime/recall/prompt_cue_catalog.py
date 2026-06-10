#!/usr/bin/env python3
"""Prompt cue term and pattern catalogs for foreground recall.

This module owns static cue surfaces only. Keep prompt intent, gating,
and source-boundary decisions in ``prompt_cues.py`` so new cue families do
not quietly bloat the hot-path policy owner.
"""

from __future__ import annotations

import re

CONCEPT_EXPANSION_MAX_TERMS = 14
SEMANTIC_GATE_CUE_DECISIONS = {"scent", "evidence"}
SEMANTIC_GATE_ALIAS_DECISIONS = {"background_only", "scent", "evidence"}
SEMANTIC_EVIDENCE_TERMS = {
    "最后",
    "latest",
    "last reply",
    "exact",
    "quote",
    "source",
    "evidence",
    "citation",
    "cite",
    "source-backed",
    "source-backed evidence",
    "source evidence",
    "clean source",
    "verbatim",
    "exact wording",
    "original wording",
    "原文",
    "原话",
    "证据",
    "引用",
    "行号",
    "你之前说过",
    "我之前说过",
}

SOURCE_EVIDENCE_REQUEST_TERMS = {
    "cite",
    "cites",
    "cited",
    "citation",
    "source-backed",
    "source-backed evidence",
    "source evidence",
    "clean source",
    "verbatim",
    "exact wording",
    "original wording",
    "原文",
    "原话",
    "证据",
    "引用",
    "行号",
}

NATURAL_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(找一下|查一下|找找|查查|看看).{0,24}(之前|前面|刚才|上次|说过|那段|那句|结论|判断|原话|原文)",
        r"(之前|前面|刚才|上次).{0,64}(那段|那句|结论|判断|说法|怎么说|怎么表述|怎么定性|是什么|哪句|讲过|说过)",
        r"(那段|那句|那个|这个|那次|这次).{0,36}(结论|判断|说法|决定|怎么说|怎么表述|怎么定性|是什么|哪句)",
        r"(那个|这个|那条|这条).{0,24}(结论|判断|说法|决定).{0,12}(怎么说|怎么表述|是什么)",
        r"(继续).{0,36}(那个|这个|那条|这条).{0,18}(结论|判断|说法|决定)",
        r"(that|the|this).{0,24}(conclusion|decision|part|bit|quote|wording)",
        r"(last time|previously|earlier).{0,48}(conclusion|decision|said|quote|wording)",
        r"(найди|найти|вспомни|верни|достань|покажи).{0,64}(раньше|ранее|до этого|прошлый раз|предыдущий|прежн[а-я]*|говорили|говорил|сказал|формулировали|формулировка|цитата|фраза|как звучал[ао]?)",
        r"(раньше|ранее|до этого|прошлый раз|предыдущий).{0,64}(формулировали|говорили|сказали|как звучал[ао]?|какая формулировка|цитата|фраза)",
        r"(как).{0,24}(мы|ты|я).{0,32}(раньше|ранее|прошлый раз).{0,32}(формулировали|говорили|сказали|называли)",
    ]
]

NEGATIVE_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(不要|别|先别).{0,12}(引用|原话|原文|证据|source|evidence)",
        r"(只|先只).{0,8}(给|要)?\s*(scent|味道|线索)",
        r"(scent[- ]only).{0,12}(mode|context|output|please|即可|就行)",
        r"(no source|no evidence|no quote|no citation)",
        r"(do not|don't).{0,20}(cite|quote|give evidence|retrieve evidence)",
        r"(without|with no|lacking).{0,24}(source|evidence|citation|cite|cited|quote|clean source|source-backed)",
        r"(unsupported|downgrade|keep it unsupported).{0,36}(without|unless).{0,24}(source|evidence|citation|cite|cited|quote|clean source|source-backed)",
        r"(без|нет|не надо|не нужно).{0,24}(источник[а-я]*|доказательств[а-я]*|цитат[а-я]*|ссылк[а-я]*|строк[аи]? источника|source|evidence|citation|quote)",
        r"(оставь|считай|пометь|держи).{0,36}(неподтвержд[а-я]*|не подтвержд[а-я]*|unsupported).{0,36}(без|если нет|пока нет|unless).{0,24}(источник[а-я]*|доказательств[а-я]*|цитат[а-я]*|ссылк[а-я]*|source|evidence|citation|quote)",
        r"(неподтвержд[а-я]*|не подтвержд[а-я]*|неподкрепл[а-я]*|не подкрепл[а-я]*|unsupported).{0,36}(без|если нет|пока нет|unless).{0,24}(источник[а-я]*|доказательств[а-я]*|цитат[а-я]*|ссылк[а-я]*|source|evidence|citation|quote)",
    ]
]

SOURCE_EVIDENCE_REQUEST_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(can you|could you|please)\s+(cite|quote)\b",
        r"\bcite\s+.+\?",
        r"(请给|给|找回|找一下|查一下).{0,18}(source-backed|source evidence|clean source|证据|引用|原话|原文)",
        r"(source-backed|source evidence|clean source).{0,18}(evidence|quote|citation|原话|原文|证据|引用)?",
        r"(можешь|можно|дай|дайте|покажи|покажите|приведи|приведите).{0,24}(источник[а-я]*|доказательств[а-я]*|цитат[а-я]*|ссылк[а-я]*|source|evidence|citation|quote)",
        r"(с источником|со ссылкой|с цитатой|source-backed).{0,24}(доказательств[а-я]*|evidence|цитат[а-я]*|ссылк[а-я]*)?",
    ]
]

EXPLICIT_RECALL_TERMS = {
    "找回",
    "想起来",
    "想起",
    "原文",
    "原话",
    "那句",
    "这句",
    "最后回复",
    "最后的消息",
    "之前说过",
    "你说过",
    "我说过",
}

RECALL_ACTION_TERMS = {
    "找回",
    "想起来",
    "想起",
    "最后回复",
    "最后的消息",
    "之前说过",
    "你说过",
    "我说过",
}

EXACT_WORDING_TOPIC_TERMS = {
    "原文",
    "原话",
    "那句",
    "这句",
}

CURRENT_CHECKOUT_SCOPE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(current|this|new)\s+(repo|repository|checkout|workspace|project|codebase)\b",
        r"\b(repo|repository|checkout|workspace|project|codebase)\s+(right\s+now|currently)\b",
        r"(当前|现在|这个|这个新|本).{0,8}(仓库|项目|工程|代码库|checkout|repo|repository)",
    ]
]

CURRENT_CHECKOUT_FACT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(test|tests|pytest|unit tests?|build|lint|typecheck|config|configuration|script|entrypoint|command|dependency|dependencies)\b",
        r"(怎么|如何|怎样|哪里|哪个|什么|运行|测试|构建|配置|命令|脚本|入口|依赖)",
    ]
]

PRIOR_HISTORY_MARKER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(之前|前面|刚才|上次|以前|早前|旧线程|旧项目|老项目)",
        r"\b(last time|previously|earlier|prior|old thread|old project)\b",
        r"(раньше|ранее|до этого|прошлый раз|предыдущий)",
    ]
]

WEAK_DEICTIC_TERMS = {
    "之前",
    "前面",
    "刚才",
    "上次",
    "继续",
    "那个",
    "这个",
    "那篇",
    "这篇",
    "anchor",
    "vault",
    "graphify",
    "rag",
    "小海马体",
    "外置海马体",
    "记忆",
    "召回",
    "压缩",
    "compaction",
}

# Bootstrap/fallback cues for foreground spend and scent gating. Keep this
# compact and language-light: new semantic paraphrases belong in
# `semantic_triggers.jsonl` or the learned `semantic_cues.jsonl` cache, which
# `prompt_recall_context.py` folds into the same pre-gate path.
ASSOCIATIVE_CUES = {
    "联想",
    "触发",
    "钩子",
    "hook机制",
    "prompt hook",
    "UserPromptSubmit",
    "记忆",
    "召回",
}

IMPORTANCE_CUES = {
    "我很喜欢",
    "很喜欢",
    "惊艳",
    "重要",
    "别忘",
    "记住",
    "记下来",
    "值得保留",
    "以后还会用",
}

CODE_SURFACE_CUES = {
    "按钮",
    "样式",
    "hover",
    "css",
    "组件",
    "dashboard",
    "panel",
    "filter",
    "filters",
    "chart",
    "charts",
    "figma",
    "layout",
    "grid",
    "table",
    "route",
    "fixture",
    "modal",
    "navigation",
    "loading",
    "mobile",
    "card",
    "mock",
    "spacing",
    "断点",
    "间距",
    "视觉稿",
    "还原",
    "对齐",
    "接上",
    "测试",
    "单测",
    "test",
    "修 bug",
    "bug",
    "报错",
    "编译",
    "接口",
    "api",
    "实现",
    "改一下",
}

MEMORY_WRITE_NEGATION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(不是|并不是|不是要|不是让|别|不要|请勿).{0,16}(写|保存|记录|新增|创建|更新|生成|当成|变成|turn).{0,18}(记忆|memory)",
        r"(不是|并不是|不是要|不是让|别|不要|请勿).{0,16}(记忆|memory).{0,18}(写入|保存|记录|新增|创建|更新|生成)",
        r"(do not|don't|not asking|not trying).{0,32}(save|write|record|persist|remember|turn).{0,32}(memory|as memory)",
        r"(do not|don't|not asking|not trying).{0,32}(turn).{0,32}(into memory)",
    ]
]

SECRET_SURFACE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(authorization|bearer|cookie|set-cookie|api[_ -]?key|api\s+token|access[_ -]?token|private\s+key|oauth\s+secret|database\s+password|db\s+password|webhook\s+signature)\b.{0,36}\b(placeholder|mock|fixture|header|label|sample|env\.?sample|validation|ui)\b",
        r"\b(placeholder|mock|fixture|header|label|sample|validation)\b.{0,36}\b(cookie|bearer|api[_ -]?key|api\s+token|access[_ -]?token|private\s+key|oauth\s+secret|password|secret)\b",
        r"\b(authorization\s*:\s*bearer|bearer\s+[a-z0-9._~+/=-]{8,}|cookie\s*[:=]|set-cookie\b|api[_ -]?key\s*[:=]|secret\s*[:=]|password\s*[:=]|token\s*[:=])",
    ]
]

MEMORY_BOUNDARY_CONTEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(只|先只).{0,12}(看|处理|保留|要).{0,30}(外置海马体|小海马体|external hippocampus|memory boundary|recall gate|project[- ]scoped|上下文|边界)",
        r"(外置海马体|小海马体|external hippocampus|memory boundary|recall gate|project[- ]scoped).{0,20}(边界|上下文|context|scope)",
    ]
]

DECISION_CONTINUATION_CUES = {
    "该不该",
    "要不要",
    "是否",
    "是不是应该",
    "能不能",
    "哪个更适合",
    "怎么选",
    "还成立吗",
    "还成立",
    "现在怎么看",
    "怎么做比较好",
}

SEMANTIC_TRIGGER_CONTEXT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"(只|先)?继续.{0,24}(上下文|那条线|这条线|那条|这条|线索)",
        r"(那条线|这条线|上下文|线索).{0,24}(继续|接着|推进|收口)",
        r"(那条线|这条线|上下文|线索).{0,16}(继续想|想一下|想想|想清楚|想明白)",
        r"(边界|boundary).{0,24}(继续|接着|推进|收口|收一下|想一下|想想)",
        r"(继续|接着).{0,24}(边界|boundary|上下文|线索)",
        r"(继续|接着)(看|想|推进|收口|处理)",
        r"(继续|接着).{0,16}(不给|不要|别|先别).{0,10}(source|evidence|原话|原文|引用|证据)",
        r"(不要|先别).{0,12}(展开实现|实现|改代码|写代码)",
        r"(only|just).{0,24}(continue|resume).{0,48}(context|thread|line)",
        r"(continue|resume).{0,48}(that context|the context|where we left off|thread|line)",
        r"(do not|don't).{0,24}(implement|code|change)",
    ]
]

RECENCY_CUES = {
    "最近",
    "最后",
    "上次",
    "当前线程之外",
    "外面",
    "latest",
    "recent",
}

SEMANTIC_GATE_LIGHT_CUES = {
    "这个",
    "那个",
    "这些",
    "那些",
    "刚才",
    "之前",
    "上次",
    "继续",
    "进度",
    "状态",
    "怎么样",
    "做到哪",
    "还成立",
    "怎么处理",
}

TERM_WRAPPERS_RE = re.compile(
    r"(还记得|记得|之前|前面|刚才|上次|找回|想起来|想起|那句|这句|那个|这个|那篇|这篇|原话|原文|吗|嘛|呢|吧|还能|能不能)"
)

GENERIC_EVIDENCE_TERMS = frozenset("之前 前面 刚才 上次 找回 那句 这句 还能找回 能不能还是 还是 而我 还是我 这个 那个 记得 还记得".split())

CJK_CONTENT_MARKERS = {
    "重写",
    "搜索",
    "客户端",
    "市场",
    "迁移",
    "归档",
    "注册",
    "线程",
    "记忆库",
    "底座",
    "本地底座",
    "本地核心",
}

CJK_SHORT_EVIDENCE_TERMS = frozenset("压力 焦虑 难受 崩溃 害怕 孤独 家人 家庭 妈妈 爸爸 伴侣 礼物 关系 偏好".split())

GENERIC_ASSOCIATION_TERMS = {
    "当前线程",
    "前线程",
    "线程",
    "当前",
    "主题是什么",
    "关于",
}


__all__ = [
    "CONCEPT_EXPANSION_MAX_TERMS",
    "SEMANTIC_GATE_CUE_DECISIONS",
    "SEMANTIC_GATE_ALIAS_DECISIONS",
    "SEMANTIC_EVIDENCE_TERMS",
    "SOURCE_EVIDENCE_REQUEST_TERMS",
    "NATURAL_EVIDENCE_PATTERNS",
    "NEGATIVE_EVIDENCE_PATTERNS",
    "SOURCE_EVIDENCE_REQUEST_PATTERNS",
    "EXPLICIT_RECALL_TERMS",
    "RECALL_ACTION_TERMS",
    "EXACT_WORDING_TOPIC_TERMS",
    "CURRENT_CHECKOUT_SCOPE_PATTERNS",
    "CURRENT_CHECKOUT_FACT_PATTERNS",
    "PRIOR_HISTORY_MARKER_PATTERNS",
    "WEAK_DEICTIC_TERMS",
    "ASSOCIATIVE_CUES",
    "IMPORTANCE_CUES",
    "CODE_SURFACE_CUES",
    "MEMORY_WRITE_NEGATION_PATTERNS",
    "SECRET_SURFACE_PATTERNS",
    "MEMORY_BOUNDARY_CONTEXT_PATTERNS",
    "DECISION_CONTINUATION_CUES",
    "SEMANTIC_TRIGGER_CONTEXT_PATTERNS",
    "RECENCY_CUES",
    "SEMANTIC_GATE_LIGHT_CUES",
    "TERM_WRAPPERS_RE",
    "GENERIC_EVIDENCE_TERMS",
    "CJK_CONTENT_MARKERS",
    "CJK_SHORT_EVIDENCE_TERMS",
    "GENERIC_ASSOCIATION_TERMS",
]
