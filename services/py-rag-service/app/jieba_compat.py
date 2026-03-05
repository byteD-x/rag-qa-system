from __future__ import annotations

import warnings
from types import ModuleType


def load_jieba() -> ModuleType:
    """Import jieba while suppressing its known deprecation warning."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="pkg_resources is deprecated as an API.*",
            category=UserWarning,
        )
        import jieba

    return jieba
