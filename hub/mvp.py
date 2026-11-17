"""Compatibility import; implementation lives in hub.services.rounds."""
import sys
from hub.services import rounds as _implementation
sys.modules[__name__] = _implementation
