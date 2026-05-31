#!/usr/bin/env python3
"""Compatibility shim for the packaged dream delivery policy."""

from __future__ import annotations

from aippocampus_runtime.dream.delivery_policy import (
    add_dream_delivery_arguments as add_dream_delivery_arguments,
)
from aippocampus_runtime.dream.delivery_policy import dream_rollout_rate as dream_rollout_rate
from aippocampus_runtime.dream.delivery_policy import (
    prepare_dream_delivery as prepare_dream_delivery,
)
from aippocampus_runtime.dream.delivery_policy import (
    requested_dream_delivery_mode as requested_dream_delivery_mode,
)
