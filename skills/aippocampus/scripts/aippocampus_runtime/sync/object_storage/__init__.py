"""Object-storage transport helpers for sync.

`sync_object_storage.py` stays at the runtime root as the documented CLI.
Client construction and provider signing live here so additional storage
providers do not grow the flat script directory or duplicate sync policy.
"""

