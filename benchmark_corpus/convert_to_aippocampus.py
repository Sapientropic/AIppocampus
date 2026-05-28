#!/usr/bin/env python3
"""Convert public conversation datasets to AIppocampus clean-source JSONL.

Supported sources:
  - WildChat-4.8M (allenai/WildChat-4.8M)
  - ShareChat (tucnguyen/ShareChat) — requires HF access grant
  - ShareGPT JSONL dumps with {human, assistant} turn pairs
  - Local CSV/JSONL files

Output: AIppocampus clean-source messages.jsonl + turns.jsonl

Usage:
  # From HuggingFace (streaming, no full download needed):
  python convert_to_aippocampus.py --source wildchat --max-convs 200 --output ./output

  # From HuggingFace with filters:
  python convert_to_aippocampus.py --source wildchat --lang English --min-turns 3 --max-convs 500

  # From ShareChat:
  python convert_to_aippocampus.py --source sharechat --subset chatgpt --max-convs 200

  # From local ShareGPT JSONL files:
  python convert_to_aippocampus.py --source sharegpt --input ./sharegpt_raw --min-turns 2 --output ./output/sharegpt_all_multiturn
  python convert_to_aippocampus.py --source sharegpt --input ./sharegpt_raw --min-turns 2 --coding-only --output ./output/sharegpt_coding_multiturn

  # From local file:
  python convert_to_aippocampus.py --source local --input conversations.jsonl --output ./output

  # With HF mirror (if direct HF is slow):
  HF_ENDPOINT=https://hf-mirror.com python convert_to_aippocampus.py --source wildchat
"""

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def stable_id(prefix: str, *parts: str) -> str:
    """Deterministic short ID from content parts."""
    h = hashlib.sha1("|".join(parts).encode()).hexdigest()[:20]
    return f"{prefix}_{h}"


def write_jsonl(path: Path, records: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# WildChat converter
# ---------------------------------------------------------------------------

def convert_wildchat(max_convs: int = 0, lang: str | None = None,
                     min_turns: int = 1, coding_only: bool = False,
                     hf_token: str | None = None):
    """Stream WildChat-4.8M from HuggingFace and convert to AIppocampus format."""
    from datasets import load_dataset

    token = hf_token or os.environ.get("HF_TOKEN")
    ds = load_dataset("allenai/WildChat-4.8M", split="train", streaming=True,
                      token=token)

    CODING_KEYWORDS = {"python", "javascript", "typescript", "function", "debug",
                       "code", "error", "import", "class ", "refactor", "api",
                       "sql", "regex", "react", "node", "html", "css", "docker",
                       "git ", "linux", "shell", "bash", "deploy", "server",
                       "database", "algorithm", "compile", "runtime"}

    messages = []
    turns = []
    conv_count = 0
    msg_count = 0
    skipped_lang = 0
    skipped_short = 0
    skipped_coding = 0

    for row in ds:
        # Language filter
        if lang and row.get("language") != lang:
            skipped_lang += 1
            continue

        conv = row.get("conversation", [])
        n_turns = row.get("turn", len(conv) // 2)

        # Min turns filter
        if n_turns < min_turns:
            skipped_short += 1
            continue

        # Coding filter
        if coding_only:
            user_texts = " ".join(t.get("content", "") for t in conv
                                  if t.get("role") == "user").lower()
            if not any(kw in user_texts for kw in CODING_KEYWORDS):
                skipped_coding += 1
                continue

        conv_hash = row.get("conversation_hash", stable_id("conv", str(conv_count)))
        source_id = stable_id("src", conv_hash)
        ts = row.get("timestamp", "")

        turn_index = 0
        clean_ordinal = 0
        for i, turn in enumerate(conv):
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            if not content or not content.strip():
                continue

            # Track user turns for turn_index
            if role == "user":
                turn_index += 1

            msg_id = stable_id("msg", conv_hash, str(i))
            turn_id = stable_id("turn", conv_hash, str(turn_index))

            # Phase inference: first assistant message in a turn = commentary,
            # last = final_answer, middle = intermediate
            phase = ""
            if role == "assistant":
                # Look ahead to see if there's another assistant message in same turn
                for j in range(i + 1, len(conv)):
                    if conv[j].get("role") == "user":
                        break
                    if conv[j].get("role") == "assistant":
                        phase = "commentary"
                        break
                if not phase:
                    phase = "final_answer"

            msg = {
                "message_id": msg_id,
                "turn_id": turn_id,
                "source_id": source_id,
                "clean_ordinal": clean_ordinal,
                "source_line": i + 1,
                "role": role,
                "phase": phase,
                "turn_index": turn_index,
                "is_final": role == "assistant" and phase == "final_answer",
                "text": content,
                # Extra metadata for benchmark use (not in core AIppocampus schema)
                "_meta": {
                    "source_dataset": "wildchat-4.8m",
                    "original_hash": conv_hash,
                    "timestamp": ts,
                    "language": row.get("language", ""),
                    "model": row.get("model", ""),
                    "hashed_ip": row.get("hashed_ip", ""),
                },
            }
            messages.append(msg)
            clean_ordinal += 1
            msg_count += 1

        # Turn summary
        turns.append({
            "turn_id": stable_id("turn", conv_hash, "summary"),
            "source_id": source_id,
            "turn_count": turn_index,
            "user_msgs": sum(1 for t in conv if t.get("role") == "user"),
            "assistant_msgs": sum(1 for t in conv if t.get("role") == "assistant"),
        })

        conv_count += 1
        if conv_count % 50 == 0:
            print(f"  Converted {conv_count} conversations ({msg_count} messages)...",
                  file=sys.stderr)

        if max_convs and conv_count >= max_convs:
            break

    print("\nConversion complete:", file=sys.stderr)
    print(f"  Conversations: {conv_count}", file=sys.stderr)
    print(f"  Messages: {msg_count}", file=sys.stderr)
    print(f"  Skipped (lang): {skipped_lang}", file=sys.stderr)
    print(f"  Skipped (short): {skipped_short}", file=sys.stderr)
    print(f"  Skipped (not coding): {skipped_coding}", file=sys.stderr)

    return messages, turns


# ---------------------------------------------------------------------------
# ShareChat converter
# ---------------------------------------------------------------------------

def convert_sharechat(subset: str = "chatgpt", max_convs: int = 0,
                      lang: str | None = None, min_turns: int = 1,
                      hf_token: str | None = None):
    """Stream ShareChat from HuggingFace and convert to AIppocampus format.

    ShareChat is stored as CSV (one row per message), grouped by URL into
    conversations.
    """
    from datasets import load_dataset

    token = hf_token or os.environ.get("HF_TOKEN")
    ds = load_dataset("tucnguyen/ShareChat", subset, split="train",
                      streaming=True, token=token)

    # Buffer messages by conversation URL
    conv_buffer: dict[str, list[dict]] = {}
    msg_count = 0
    conv_count = 0
    skipped_lang = 0
    skipped_short = 0

    all_messages = []
    all_turns = []

    for row in ds:
        url = row.get("url", f"conv_{msg_count}")
        detected_lang = row.get("detected_language_final", "")
        role = row.get("role", "unknown")
        text = row.get("plain_text", "")
        msg_idx = row.get("message_index", 0)
        turns_count = row.get("turns_count", 1)

        if url not in conv_buffer:
            conv_buffer[url] = {
                "messages": [],
                "language": detected_lang,
                "platform": row.get("platform", subset),
                "turns_count": turns_count,
                "topic": row.get("topic", ""),
            }
        conv_buffer[url]["messages"].append({
            "role": role,
            "text": text,
            "index": msg_idx,
        })
        msg_count += 1

        # Process complete conversations periodically
        if msg_count % 1000 == 0:
            # Process conversations where we've seen all messages
            done_urls = [u for u, v in conv_buffer.items()
                         if len(v["messages"]) >= v["turns_count"]]
            for u in done_urls:
                conv_data = conv_buffer.pop(u)
                _process_sharechat_conv(u, conv_data, lang, min_turns,
                                        all_messages, all_turns)
                conv_count += 1
                skipped_lang, skipped_short  # tracked inside
            if done_urls:
                print(f"  Processed {conv_count} conversations...",
                      file=sys.stderr)

        if max_convs and conv_count >= max_convs:
            break

    # Process remaining
    for url, conv_data in conv_buffer.items():
        _process_sharechat_conv(url, conv_data, lang, min_turns,
                                all_messages, all_turns)
        conv_count += 1

    print("\nConversion complete:", file=sys.stderr)
    print(f"  Conversations: {conv_count}", file=sys.stderr)
    print(f"  Messages: {len(all_messages)}", file=sys.stderr)

    return all_messages, all_turns


def _process_sharechat_conv(url, conv_data, lang_filter, min_turns,
                            all_messages, all_turns):
    """Convert a single ShareChat conversation."""
    global _skipped_lang, _skipped_short
    if lang_filter and conv_data["language"] != lang_filter:
        return
    if conv_data["turns_count"] < min_turns:
        return

    msgs = sorted(conv_data["messages"], key=lambda m: m["index"])
    conv_hash = hashlib.sha1(url.encode()).hexdigest()[:12]
    source_id = stable_id("src", conv_hash)

    turn_index = 0
    clean_ordinal = 0
    for i, m in enumerate(msgs):
        role = m["role"]
        text = m["text"]
        if not text or not text.strip():
            continue
        if role == "user":
            turn_index += 1

        msg_id = stable_id("msg", conv_hash, str(i))
        turn_id = stable_id("turn", conv_hash, str(turn_index))

        phase = ""
        if role == "assistant":
            # Check if last assistant message in this turn
            remaining = msgs[i+1:]
            has_more_asst = any(r["role"] == "assistant" for r in remaining
                               if r["index"] == m["index"])
            phase = "commentary" if has_more_asst else "final_answer"

        all_messages.append({
            "message_id": msg_id,
            "turn_id": turn_id,
            "source_id": source_id,
            "clean_ordinal": clean_ordinal,
            "source_line": i + 1,
            "role": role,
            "phase": phase,
            "turn_index": turn_index,
            "is_final": role == "assistant" and phase == "final_answer",
            "text": text,
            "_meta": {
                "source_dataset": f"sharechat-{conv_data['platform']}",
                "original_url": url,
                "language": conv_data["language"],
                "topic": conv_data.get("topic", ""),
            },
        })
        clean_ordinal += 1

    all_turns.append({
        "turn_id": stable_id("turn", conv_hash, "summary"),
        "source_id": source_id,
        "turn_count": turn_index,
        "user_msgs": sum(1 for m in msgs if m["role"] == "user"),
        "assistant_msgs": sum(1 for m in msgs if m["role"] == "assistant"),
    })


# ---------------------------------------------------------------------------
# ShareGPT-Chinese-English-90k converter
# ---------------------------------------------------------------------------

def convert_sharegpt(input_path: str, max_convs: int = 0, min_turns: int = 1,
                     coding_only: bool = False):
    """Convert ShareGPT format: {conversation_id, category, conversation: [{human, assistant}]}.

    Accepts a single JSONL file or a directory of JSONL files.
    """
    in_path = Path(input_path)
    files = sorted(in_path.glob("*.jsonl")) if in_path.is_dir() else [in_path]

    CODING_CATEGORIES = {
        "program and code", "computer science", "computer science and technology",
        "math", "technology",
    }
    CODING_KEYWORDS = {"python", "javascript", "typescript", "function", "debug",
                       "code", "error", "import", "class ", "refactor", "api",
                       "sql", "regex", "react", "node", "html", "css", "docker",
                       "git ", "linux", "shell", "bash", "deploy", "server",
                       "database", "algorithm", "compile", "runtime", "java",
                       "golang", "rust", "swift", "kotlin", "ruby", "php"}

    messages = []
    turns = []
    conv_count = 0
    msg_count = 0
    skipped_short = 0
    skipped_coding = 0
    skipped_empty = 0

    for fp in files:
        print(f"  Processing {fp.name}...", file=sys.stderr)
        with open(fp, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue

                conv_id = row.get("conversation_id", row.get("id", f"sg_{conv_count}"))
                raw_cat = row.get("category", "unknown")
                if isinstance(raw_cat, list):
                    category = ", ".join(str(c) for c in raw_cat).strip()
                else:
                    category = str(raw_cat).strip()

                raw_conv = row.get("conversation", [])
                if not raw_conv:
                    skipped_empty += 1
                    continue

                # Convert [{human, assistant}] → [{role, content}]
                conv = []
                for entry in raw_conv:
                    human_text = entry.get("human", "")
                    asst_text = entry.get("assistant", "")
                    if human_text and human_text.strip():
                        conv.append({"role": "user", "content": human_text.strip()})
                    if asst_text and asst_text.strip():
                        conv.append({"role": "assistant", "content": asst_text.strip()})

                if not conv:
                    skipped_empty += 1
                    continue

                # Count turns (user-assistant pairs)
                user_msgs = sum(1 for t in conv if t["role"] == "user")
                turn_pairs = user_msgs  # each user msg = 1 turn

                if turn_pairs < min_turns:
                    skipped_short += 1
                    continue

                # Coding filter
                if coding_only:
                    cat_match = category.lower() in CODING_CATEGORIES
                    if not cat_match:
                        user_texts = " ".join(t["content"] for t in conv
                                              if t["role"] == "user").lower()
                        if not any(kw in user_texts for kw in CODING_KEYWORDS):
                            skipped_coding += 1
                            continue

                conv_hash = hashlib.sha1(conv_id.encode()).hexdigest()[:12]
                source_id = stable_id("src", conv_hash)

                turn_index = 0
                clean_ordinal = 0
                for i, turn in enumerate(conv):
                    role = turn["role"]
                    content = turn["content"]
                    if role == "user":
                        turn_index += 1

                    msg_id = stable_id("msg", conv_hash, str(i))
                    turn_id = stable_id("turn", conv_hash, str(turn_index))

                    # Phase: last assistant in turn = final_answer
                    phase = ""
                    if role == "assistant":
                        for j in range(i + 1, len(conv)):
                            if conv[j]["role"] == "user":
                                break
                            if conv[j]["role"] == "assistant":
                                phase = "commentary"
                                break
                        if not phase:
                            phase = "final_answer"

                    messages.append({
                        "message_id": msg_id,
                        "turn_id": turn_id,
                        "source_id": source_id,
                        "clean_ordinal": clean_ordinal,
                        "source_line": i + 1,
                        "role": role,
                        "phase": phase,
                        "turn_index": turn_index,
                        "is_final": role == "assistant" and phase == "final_answer",
                        "text": content,
                        "_meta": {
                            "source_dataset": "sharegpt-90k",
                            "source_file": fp.name,
                            "conversation_id": conv_id,
                            "category": category,
                        },
                    })
                    clean_ordinal += 1
                    msg_count += 1

                turns.append({
                    "turn_id": stable_id("turn", conv_hash, "summary"),
                    "source_id": source_id,
                    "turn_count": turn_index,
                    "user_msgs": user_msgs,
                    "assistant_msgs": sum(1 for t in conv if t["role"] == "assistant"),
                })

                conv_count += 1
                if conv_count % 500 == 0:
                    print(f"  Converted {conv_count} conversations ({msg_count} messages)...",
                          file=sys.stderr)

                if max_convs and conv_count >= max_convs:
                    break

        if max_convs and conv_count >= max_convs:
            break

    print("\nConversion complete:", file=sys.stderr)
    print(f"  Conversations: {conv_count}", file=sys.stderr)
    print(f"  Messages: {msg_count}", file=sys.stderr)
    print(f"  Skipped (empty): {skipped_empty}", file=sys.stderr)
    print(f"  Skipped (short): {skipped_short}", file=sys.stderr)
    print(f"  Skipped (not coding): {skipped_coding}", file=sys.stderr)

    return messages, turns


# ---------------------------------------------------------------------------
# Local file converter
# ---------------------------------------------------------------------------

def convert_local(input_path: str):
    """Convert a local JSONL file with {conversations: [{role, content}]} format."""
    messages = []
    turns = []

    with open(input_path, "r", encoding="utf-8") as f:
        for conv_idx, line in enumerate(f):
            row = json.loads(line)
            convs = row.get("conversations", row.get("conversation", []))

            conv_hash = hashlib.sha1(str(conv_idx).encode()).hexdigest()[:12]
            source_id = stable_id("src", conv_hash)
            turn_index = 0
            clean_ordinal = 0

            for i, turn in enumerate(convs):
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
                if not content or not content.strip():
                    continue
                if role == "user":
                    turn_index += 1

                msg_id = stable_id("msg", conv_hash, str(i))
                turn_id = stable_id("turn", conv_hash, str(turn_index))
                phase = "final_answer" if role == "assistant" else ""

                messages.append({
                    "message_id": msg_id,
                    "turn_id": turn_id,
                    "source_id": source_id,
                    "clean_ordinal": clean_ordinal,
                    "source_line": i + 1,
                    "role": role,
                    "phase": phase,
                    "turn_index": turn_index,
                    "is_final": role == "assistant",
                    "text": content,
                    "_meta": {
                        "source_dataset": "local",
                        "original_index": conv_idx,
                    },
                })
                clean_ordinal += 1

            turns.append({
                "turn_id": stable_id("turn", conv_hash, "summary"),
                "source_id": source_id,
                "turn_count": turn_index,
                "user_msgs": sum(1 for t in convs if t.get("role") == "user"),
                "assistant_msgs": sum(1 for t in convs if t.get("role") == "assistant"),
            })

    print(f"Converted {len(turns)} conversations, {len(messages)} messages",
          file=sys.stderr)
    return messages, turns


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        choices=["wildchat", "sharechat", "sharegpt", "local"],
                        help="Data source")
    parser.add_argument("--subset", default=None,
                        help="ShareChat subset: chatgpt, claude, gemini, grok, perplexity")
    parser.add_argument("--input", default=None,
                        help="Local input file (for --source local)")
    parser.add_argument("--output", default="./output",
                        help="Output directory")
    parser.add_argument("--max-convs", type=int, default=0,
                        help="Max conversations to convert (0 = all)")
    parser.add_argument("--lang", default=None,
                        help="Language filter (e.g. English, Chinese)")
    parser.add_argument("--min-turns", type=int, default=1,
                        help="Minimum turns per conversation")
    parser.add_argument("--coding-only", action="store_true",
                        help="Only include conversations with coding content")
    parser.add_argument("--strip-meta", action="store_true",
                        help="Strip _meta field from output (for pure AIppocampus schema)")

    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    if args.source == "wildchat":
        messages, turns = convert_wildchat(
            max_convs=args.max_convs,
            lang=args.lang,
            min_turns=args.min_turns,
            coding_only=args.coding_only,
        )
    elif args.source == "sharechat":
        if not args.subset:
            print("Error: --subset required for sharechat "
                  "(chatgpt|claude|gemini|grok|perplexity)", file=sys.stderr)
            sys.exit(1)
        messages, turns = convert_sharechat(
            subset=args.subset,
            max_convs=args.max_convs,
            lang=args.lang,
            min_turns=args.min_turns,
        )
    elif args.source == "sharegpt":
        if not args.input:
            print("Error: --input required for sharegpt source "
                  "(path to ShareGPT JSONL file or directory)", file=sys.stderr)
            sys.exit(1)
        messages, turns = convert_sharegpt(
            input_path=args.input,
            max_convs=args.max_convs,
            min_turns=args.min_turns,
            coding_only=args.coding_only,
        )
    elif args.source == "local":
        if not args.input:
            print("Error: --input required for local source", file=sys.stderr)
            sys.exit(1)
        messages, turns = convert_local(args.input)

    # Optionally strip _meta
    if args.strip_meta:
        for m in messages:
            m.pop("_meta", None)

    # Write output
    write_jsonl(out / "messages.jsonl", messages)
    write_jsonl(out / "turns.jsonl", turns)

    # Summary
    print(f"\nOutput written to {out}/")
    print(f"  messages.jsonl: {len(messages)} messages")
    print(f"  turns.jsonl: {len(turns)} conversations")

    # Quick stats
    roles = defaultdict(int)
    langs = defaultdict(int)
    for m in messages:
        roles[m["role"]] += 1
        meta = m.get("_meta", {})
        if "language" in meta:
            langs[meta["language"]] += 1

    print(f"\nRole distribution: {dict(roles)}")
    if langs:
        top = sorted(langs.items(), key=lambda x: -x[1])[:5]
        print(f"Top languages: {top}")


if __name__ == "__main__":
    main()
