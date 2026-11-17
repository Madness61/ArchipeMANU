"""Compatibility import; implementation lives in hub.services.progression."""
import sys
from hub.services import progression as _implementation
sys.modules[__name__] = _implementation
