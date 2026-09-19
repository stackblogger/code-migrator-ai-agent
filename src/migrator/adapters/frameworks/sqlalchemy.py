"""SQLAlchemy: model classes with __tablename__ -> tables and columns."""

from migrator.adapters.frameworks.base import Extraction, FrameworkAdapter, SourceFile
from migrator.adapters.frameworks.py_syntax import call, class_assignments, classes, literal
from migrator.adapters.languages.treesitter import text
from migrator.concepts.keys import column_key
from migrator.concepts.models import ConceptKind

COLUMN_FACTORIES = {"mapped_column", "Column", "sa.Column", "db.Column", "sqlalchemy.Column"}


class SqlAlchemyAdapter(FrameworkAdapter):
    name = "sqlalchemy"
    language = "python"
    packages = {"sqlalchemy"}

    def extract(self, files: list[SourceFile]) -> Extraction:
        result = Extraction()
        for file in files:
            for cls in classes(file.root):
                fields = list(class_assignments(cls, file.source))
                table = next(
                    (literal(v, file.source) for n, _, v, _ in fields if n == "__tablename__"), None
                )
                if not table:
                    continue
                class_name = text(cls.child_by_field_name("name"), file.source)
                result.nodes.append(self.node(ConceptKind.TABLE, table, class_name, file, cls))
                for name, annotation, value, statement in fields:
                    found = call(value, file.source)
                    if found and found.name in COLUMN_FACTORIES:
                        attrs, column = _column(name, annotation, found, file.source)
                        key = column_key(table, column)
                        result.nodes.append(
                            self.node(
                                ConceptKind.COLUMN,
                                key,
                                f"{class_name}.{name}",
                                file,
                                statement,
                                **attrs,
                            )
                        )
        return result


def _column(attribute: str, annotation: str | None, found, source: bytes) -> tuple[dict, str]:
    first = literal(found.args[0], source) if found.args else None
    column = first if isinstance(first, str) else attribute
    primary = literal(found.kwargs.get("primary_key"), source) is True
    if "nullable" in found.kwargs:
        nullable = literal(found.kwargs["nullable"], source) is True
    elif annotation:  # Mapped[str | None] -> nullable, Mapped[str] -> not null
        nullable = "None" in annotation or "Optional[" in annotation
    else:
        nullable = not primary  # plain Column() is nullable by default
    attrs: dict[str, bool | str] = {
        "nullable": False if primary else nullable,
        "unique": literal(found.kwargs.get("unique"), source) is True,
        "primary_key": primary,
    }
    for arg in found.args:
        foreign = call(arg, source)
        if foreign and foreign.name.endswith("ForeignKey") and foreign.args:
            target = literal(foreign.args[0], source) or ""
            attrs["references"] = target.split(".")[0]
    return attrs, column
