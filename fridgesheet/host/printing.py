"""Print a PDF duplex on letter paper, and list printers.

Linux: CUPS (`lp`, `lpstat`). Windows: SumatraPDF (bundled by the installer; FRIDGESHEET_SUMATRA
overrides its path) because it is the one PDF printer on Windows that is silent, honours
duplex, and returns an exit code. `printer=None` means the system default on both.
"""
from __future__ import annotations

from . import IS_WINDOWS
from . import PrintError  # noqa: F401  re-exported

if IS_WINDOWS:
    from . import printing_windows as _impl
else:
    from . import printing_linux as _impl

list_printers = _impl.list_printers
default_printer = _impl.default_printer
print_pdf = _impl.print_pdf
