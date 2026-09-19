"""Framework adapters. Add a new framework by writing an adapter and adding it here."""

from migrator.adapters.frameworks.base import Extraction, FrameworkAdapter, SourceFile, load_files
from migrator.adapters.frameworks.fastapi import FastApiAdapter
from migrator.adapters.frameworks.nestjs import NestJsAdapter
from migrator.adapters.frameworks.sqlalchemy import SqlAlchemyAdapter
from migrator.adapters.frameworks.typeorm import TypeOrmAdapter


def default_framework_adapters() -> list[FrameworkAdapter]:
    return [NestJsAdapter(), TypeOrmAdapter(), FastApiAdapter(), SqlAlchemyAdapter()]


__all__ = [
    "Extraction",
    "FrameworkAdapter",
    "SourceFile",
    "default_framework_adapters",
    "load_files",
]
