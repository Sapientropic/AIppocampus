"""Package owners for clean-source artifacts and semantic source sidecars.

Top-level ``build_*`` and ``search_*`` scripts stay as compatibility shims so
direct script execution and old imports keep working. New runtime imports
should use this package to avoid growing another flat source API surface.
"""

