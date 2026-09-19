"""Language adapters. Add a new language by writing an adapter and adding it here."""

from migrator.adapters.languages.base import LanguageAdapter
from migrator.adapters.languages.python import PythonAdapter
from migrator.adapters.languages.typescript import TypeScriptAdapter


def default_adapters() -> list[LanguageAdapter]:
    return [TypeScriptAdapter(), PythonAdapter()]


__all__ = ["LanguageAdapter", "PythonAdapter", "TypeScriptAdapter", "default_adapters"]
