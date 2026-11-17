"""Compatibility import; implementation lives in hub.integrations.console."""
import sys
from hub.integrations import console as _implementation
sys.modules[__name__] = _implementation
