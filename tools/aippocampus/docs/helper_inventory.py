from __future__ import annotations

RUNTIME_CORE = "skills/aippocampus/scripts/aippocampus_runtime/core.py"
SOURCE_IO_KERNEL = "skills/aippocampus/scripts/aippocampus_runtime/source/io_kernel.py"

HELPER_NAME_TO_FAMILY = {
    "_without_empty": "without_empty",
    "_as_list": "as_list",
    "list_or_empty": "as_list",
    "string_list_or_empty": "as_list",
    "_as_dict": "as_mapping",
    "_as_mapping": "as_mapping",
    "dict_or_empty": "as_mapping",
    "_block": "schema_block",
    "schema_block": "schema_block",
    "_blocker_codes": "schema_blocker_codes",
    "schema_blocker_codes": "schema_blocker_codes",
    "_stable_id": "stable_id",
    "stable_id": "stable_id",
    "stable_hash": "stable_hash",
    "load_json": "json_load",
    "load_json_dict": "json_load",
    "iter_jsonl": "jsonl_read",
    "iter_jsonl_dict_rows": "jsonl_read",
    "iter_jsonl_dict_rows_with_line_numbers": "jsonl_read",
    "load_jsonl_dict_rows": "jsonl_read",
    "write_jsonl": "jsonl_write",
    "write_jsonl_dict_rows": "jsonl_write",
    "_write_json_atomic": "json_atomic_write",
    "write_json_atomic": "json_atomic_write",
    "source_ref_key": "source_ref_key",
    "safe_float": "safe_float",
    "parse_utc": "parse_utc",
}

CANONICAL_HELPER_PATHS = {
    "as_list": {RUNTIME_CORE},
    "as_mapping": {RUNTIME_CORE},
    "schema_block": {RUNTIME_CORE},
    "schema_blocker_codes": {RUNTIME_CORE},
    "json_load": {SOURCE_IO_KERNEL},
    "jsonl_read": {SOURCE_IO_KERNEL},
    "jsonl_write": {SOURCE_IO_KERNEL},
    "json_atomic_write": {SOURCE_IO_KERNEL},
    "source_ref_key": {SOURCE_IO_KERNEL},
    "safe_float": {SOURCE_IO_KERNEL},
    "parse_utc": {SOURCE_IO_KERNEL},
}
