from __future__ import annotations

# src/pyfxp/__init__.py

"""
pyfxp — Hardware-indicative fixed-point arithmetic and HDL generation.

Public API
----------
    from pyfxp import FixedPoint

The graph, node, and rtlgen modules are loaded as compiled extensions
in the installed package. In the dev repo they are imported directly
as .py source files.
"""

import os

from .fix_point import FixedPoint
from .types import SignType

# In the dev repo the closed-source modules are plain .py files and
# import fine. In the installed package they are compiled .so/.pyd
# extensions. Either way the import below works the same.
#
# If neither source nor binary is present (e.g. someone installs on an
# unsupported platform) we raise a clear error rather than an opaque one.
try:
    from . import graph, node, rtlgen
except ImportError as e:
    import platform as _platform
    import sys as _sys
    _dev = os.path.isfile(os.path.join(os.path.dirname(__file__), "graph.py"))
    if _dev:
        # Source files exist but failed to import — a real bug
        raise
    raise ImportError(
        "\n\npyfxp: could not load compiled extension on this platform."
        "\n  Python  : " + _sys.version +
        "\n  Platform: " + _platform.platform() +
        "\n\n  Pre-built binaries are included for:"
        "\n    - macOS arm64 (Apple Silicon) — Python 3.9, 3.10, 3.11, 3.12"
        "\n    - Linux x86_64               — Python 3.9, 3.10, 3.11, 3.12"
        "\n    - Windows x86_64             — Python 3.9, 3.10, 3.11, 3.12"
        "\n\n  If you need support for another platform, open an issue:"
        "\n  https://github.com/yourname/pyfxp/issues"
        "\n\n  Original error: " + str(e)
    ) from None

__all__ = ["FixedPoint", "SignType"]
__version__ = "0.1.0"