from __future__ import annotations


def payload() -> dict:
    # compatibility owner: #2699; removal: after legacy clients stop reading it;
    # default exposure: detail/operator only, never compact foreground.
    return {"legacy_recall_selector": "sel_123"}
