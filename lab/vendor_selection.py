"""Compatibility imports for historical lab scripts."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.pvbuild.vendor import copy_selection, module_closure, resolve_firmware, select_firmware
