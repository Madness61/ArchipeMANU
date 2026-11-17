"""Compatibility import; implementation lives in hub.integrations.archipelago."""
import sys
from hub.integrations import archipelago as _implementation
sys.modules[__name__] = _implementation
