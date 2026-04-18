# src/pyfxp/__init__.py

"""
pyfxp — Hardware-indicative fixed-point arithmetic and HDL generation.

Public API
----------
    from pyfxp import FixedPoint

The graph, node, and rtlgen modules are loaded as compiled extensions.
If a binary for your platform is not bundled in this release, a clear
ImportError is raised with instructions.
"""

from .fix_point import FixedPoint
from .types import SignType

# Attempt to import compiled modules, give a clear error if missing.
# This happens if someone installs on a platform for which no binary
# was included in the release.
try:
    from . import graph, node, rtlgen
except ImportError as e:
    import platform, sys
    _plat = platform.platform()
    _py   = sys.version
    raise ImportError(
        f"\n\npyfxp: could not load compiled extension on this platform.\n"
        f"  Python : {_py}\n"
        f"  Platform: {_plat}\n\n"
        f"  Pre-built binaries are included for:\n"
        f"    - macOS arm64 (Apple Silicon) — Python 3.10, 3.11, 3.12\n"
        f"    - Linux x86_64               — Python 3.10, 3.11, 3.12\n"
        f"    - Windows x86_64             — Python 3.10, 3.11, 3.12\n\n"
        f"  If you need support for another platform, please open an issue:\n"
        f"  https://github.com/yourname/pyfxp/issues\n\n"
        f"  Original error: {e}"
    ) from None

__all__ = ["FixedPoint", "SignType"]
__version__ = "0.1.0"
