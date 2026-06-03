# Multimodal Memory Benchmark Map

Status: source-shape comparison map for GitHub #534 and the #528 multimodal
source-backed recall track.

Verified source links on 2026-06-03:

- [HippoCamp project](https://hippocamp-ai.github.io/) and
  [preprint](https://arxiv.org/abs/2604.01221)
- [MemLens paper](https://arxiv.org/abs/2605.14906) and
  [code/data repository](https://github.com/xrenaf/MEMLENS)
- [ATM-Bench project](https://atmbench.github.io/) and
  [repository](https://github.com/JingbiaoMei/ATM-Bench)
- [EgoMemReason project](https://egomemreason.github.io/) and
  [paper](https://arxiv.org/abs/2605.09874)
- [MyEgo paper](https://arxiv.org/abs/2604.01966)
- [Ego4D episodic-memory benchmark](https://ego4d-data.org/docs/benchmarks/episodic-memory/)
- [UniDoc-Bench paper](https://arxiv.org/abs/2510.03663)
- [PersonaVLM project](https://personavlm.github.io/) and
  [paper](https://arxiv.org/abs/2604.13074)
- [Mem-Gallery paper](https://arxiv.org/abs/2601.03515)
- [MMRC paper](https://arxiv.org/abs/2502.11903)

## Purpose

ATM-Bench is a useful reference for staged multimodal personal-memory-corpus
QA, but it should not become the only mental model for #528. AIppocampus needs
to borrow pressure tests by source shape:

- conversation history with uploaded/selected media;
- staged multimodal memory corpus;
- personal filesystem or device-scale source infrastructure;
- egocentric video / visual life memory;
- document-centric knowledge sources;
- long-term personalization and profile evolution.

This map is not a leaderboard and does not claim AIppocampus performance on any
external benchmark. It decides which failure modes are worth reproducing in
public-safe synthetic fixtures, which belong in private real-history smokes,
and which require a future external adapter before they can support a public
claim.

## Recommended Mapping

| Benchmark family | Source shape | Stresses | AIppocampus fit | Claim boundary |
| --- | --- | --- | --- | --- |
| HippoCamp | Personal-computer file systems with many file types and evidence-grounded QA. | Device-scale search, multimodal grounding, cross-file reasoning, profile inference. | Future personal-file infrastructure and private-real-history evaluation; useful context for #531 beyond small staged fixtures. | Not primarily conversational continuity; do not treat file-system profile scores as chat/upload recall proof. |
| MemLens | Multimodal multi-session conversations. | Visual evidence retention, multi-session reasoning, temporal reasoning, knowledge update, answer refusal. | Strong reference for #532 conversational media-ingest recall and text-only shortcut controls. | Conversation benchmark, not device-scale filesystem or broad life-wide source registry proof. |
| ATM-Bench | Staged long-term personalized memory corpus with images, videos, emails, evidence ids, Oracle, and NIAH pools. | Referential queries, source conflicts, cross-modal joins, abstention, retrieval vs supplied-pool synthesis. | #531 corpus-style retrieval fixture and #533 NIAH-style evidence-pool fixture. | Staged corpus QA is not conversational upload-history, product privacy behavior, or an ATM-Bench score without a real adapter. |
| EgoMemReason / MyEgo / Ego4D episodic memory | Egocentric video and visual life-memory traces. | Long-horizon visual recall, temporal localization, object/entity/event memory, "my things / my past" questions. | Future visual source-reopen and life-memory fixtures, especially image/video-first questions like "where did I leave X?". | Mostly visual/egocentric; it does not automatically cover chat, email, receipt, calendar, and document mixtures. |
| UniDoc-Bench | Document-centric multimodal RAG over pages with text, tables, and figures. | Evidence linking across document modalities, retrieval/generation protocol design, logical comparison/summarization. | Future knowledge-source/document-source fixtures for #512/#514/#516-style work. | Not personal memory; do not use document QA as life-wide continuity proof. |
| Persona-MME / PersonaVLM | Long-term personalized multimodal interactions and evolving user alignment. | Preference evolution, profile inference, response alignment, remembered interaction summaries. | Future AIppo/persona/capability-package evaluation, with source-backed profile constraints. | Personalization is not source truth; do not import unsourced profile claims as an authority layer. |
| Mem-Gallery / MMRC | Long-term multimodal conversations with visual/textual dependencies. | Memory extraction, memory reasoning, information update, image management, recall, answer refusal. | Broader neighbors for #532 and future conversation-history fixtures. | Protocols need adapter-level inspection before source-backed claims; note-taking or summarized memory is not source reopen. |

## Immediate Slice Decisions

| AIppocampus slice | Borrow from | Why |
| --- | --- | --- |
| #531 corpus-style multimodal retrieval | ATM-Bench first; HippoCamp later for device-scale pressure. | #531 needs staged source registration, derived artifacts as navigation, retrieval, and source reopen. HippoCamp adds scale and personal-file heterogeneity once the source layer can handle it. |
| #532 conversational media-ingest recall | MemLens, Mem-Gallery, MMRC. | These stress conversation traces where the user's wording and media evidence both matter, plus refusal/update behavior. |
| #533 NIAH-style evidence-pool evaluation | ATM-Bench NIAH. | Fixed pools separate answer synthesis and source selection from retrieval; this catches stale/conflicting-source reasoning failures even when the right evidence is present. |
| #541 source manifest and media-origin policy | ATM-Bench, MemLens, HippoCamp, and egocentric/document-source families. | Runtime source handling needs one contract for original source anchors, origin policy, task-scoped consent, and derived-artifact provenance before fixtures become product paths. |
| Future visual life-memory fixtures | EgoMemReason, MyEgo, Ego4D episodic memory. | These are better references for image/video-first temporal and spatial memory than staged email/image corpus QA. |
| Future document/knowledge-source fixtures | UniDoc-Bench. | Document tables, figures, and page-local evidence should inform knowledge-source contracts, not personal-memory claims. |
| Future profile/persona fixtures | PersonaVLM / Persona-MME plus HippoCamp profiling tasks. | Profile inference must stay source-backed and reversible; profile benchmarks are useful only if they preserve evidence and update boundaries. |

The #541 runtime source contract is
[`../../../architecture/multimodal-source-manifests.md`](../../../architecture/multimodal-source-manifests.md).
It keeps captions, OCR, tags, and schema rows as navigation artifacts while
original source anchors remain the audit boundary.

## Claim-Boundary Traps

- Staged corpus QA is not conversational upload recall. A benchmark directory
  full of images/videos/emails cannot prove that an agent handled media the
  user sent in a live conversation.
- Caption, OCR, tag, note, or summarized memory is not source truth. These
  artifacts can route search, but visual/document claims still need source
  reopen unless the fixture explicitly owns frozen truth labels.
- Visual life-memory benchmarks do not automatically cover chat, email,
  receipt, calendar, and document source mixtures.
- Profile or personalization benchmarks can reward plausible user modeling
  without requiring source-auditable claims. AIppocampus should treat profile
  findings as hypotheses until source-backed.
- Supplied-pool/NIAH results do not measure retrieval quality. They measure
  whether the answerer can select, reason over, and cite the right evidence
  after retrieval has been removed from the task.
- A public synthetic fixture can prove a contract shape, but not natural
  distribution coverage or private real-history lift.

## Adapter Readiness Notes

Before any public claim against one of these external benchmarks, add a dated
adapter report that names:

- dataset/version/license and local artifact policy;
- source visibility in the prediction prompt;
- whether answers, evidence ids, or scoring labels are hidden from the agent;
- whether raw media/documents are reopened or only captions/OCR/tags are used;
- negative controls, ablations, or closed-book controls;
- exact `cannot_claim` boundaries and known fairness gaps.

Until then, this map is the canonical #528 benchmark-family routing note, not
evidence of external benchmark performance.
