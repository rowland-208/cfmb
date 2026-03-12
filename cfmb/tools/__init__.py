import importlib
import pkgutil

from cfmb.tools.base import Tool

_registry: dict[str, Tool] = {}


def _discover():
    """Import all modules in this package to trigger subclass registration."""
    for info in pkgutil.iter_modules(__path__):
        if info.name == "base":
            continue
        importlib.import_module(f"{__name__}.{info.name}")
    for cls in Tool.__subclasses__():
        instance = cls()
        _registry[instance.name] = instance


def get_tools() -> list[Tool]:
    """Return all enabled tool instances."""
    if not _registry:
        _discover()
    return [t for t in _registry.values() if t.enabled()]


def get_tool(name: str) -> Tool | None:
    """Look up a tool by name."""
    if not _registry:
        _discover()
    return _registry.get(name)
