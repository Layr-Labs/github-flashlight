"""Language-specific discovery plugins."""

from .base import LanguagePlugin
from .go import GoPlugin
from .python import PythonPlugin
from .typescript import TypeScriptPlugin
from .rust import RustPlugin

# Plugin registry: each plugin knows how to discover components for its language.
# Order matters — first match wins for a given manifest file.
ALL_PLUGINS: list[LanguagePlugin] = [
    GoPlugin(),
    PythonPlugin(),
    TypeScriptPlugin(),
    RustPlugin(),
]

__all__ = [
    "LanguagePlugin",
    "GoPlugin",
    "PythonPlugin",
    "TypeScriptPlugin",
    "RustPlugin",
    "ALL_PLUGINS",
]
