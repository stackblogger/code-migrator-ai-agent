"""TypeORM: @Entity classes -> tables and columns (with nullable / unique / primary key)."""

from migrator.adapters.frameworks.base import Extraction, FrameworkAdapter, SourceFile
from migrator.adapters.frameworks.ts_syntax import ClassInfo, Decorator, classes, literal, members
from migrator.adapters.languages.treesitter import text
from migrator.concepts.keys import column_key
from migrator.concepts.models import ConceptKind

PRIMARY = {"PrimaryGeneratedColumn", "PrimaryColumn"}
COLUMNS = PRIMARY | {
    "Column",
    "CreateDateColumn",
    "UpdateDateColumn",
    "DeleteDateColumn",
    "VersionColumn",
}
# Relations that own a foreign key column. OneToOne owns it only with @JoinColumn.
JOIN_RELATIONS = {"ManyToOne"}


class TypeOrmAdapter(FrameworkAdapter):
    name = "typeorm"
    language = "typescript"
    packages = {"typeorm"}

    def extract(self, files: list[SourceFile]) -> Extraction:
        result = Extraction()
        entities = [
            (file, cls)
            for file in files
            for cls in classes(file.root, file.source)
            if any(d.name == "Entity" for d in cls.decorators)
        ]
        tables = {cls.name: self._table_name(file, cls, result) for file, cls in entities}
        for file, cls in entities:
            table = tables[cls.name]
            result.nodes.append(self.node(ConceptKind.TABLE, table, cls.name, file, cls.node))
            for member in members(cls.node, file.source):
                self._column(file, cls, member, table, tables, result)
        return result

    def _table_name(self, file: SourceFile, cls: ClassInfo, result: Extraction) -> str:
        entity = next(d for d in cls.decorators if d.name == "Entity")
        value = literal(entity.args[0], file.source) if entity.args else None
        if isinstance(value, dict):
            value = value.get("name")
        if isinstance(value, str) and value:
            return value
        result.notes.append(
            f"typeorm: no table name on {cls.name} in {file.path}, using the class name"
        )
        return cls.name

    def _column(self, file, cls, member, table, tables, result: Extraction) -> None:
        names = {d.name for d in member.decorators}
        column_deco = next((d for d in member.decorators if d.name in COLUMNS), None)
        if column_deco:
            options = _options(column_deco, file.source)
            primary = column_deco.name in PRIMARY
            column = options.get("name") or member.name
            nullable = False if primary else bool(options.get("nullable", False))
            attrs = {
                "nullable": nullable,
                "unique": bool(options.get("unique", False)),
                "primary_key": primary,
            }
        elif names & JOIN_RELATIONS:
            relation = next(d for d in member.decorators if d.name in JOIN_RELATIONS)
            options = _options(relation, file.source)
            join = next((d for d in member.decorators if d.name == "JoinColumn"), None)
            join_name = _options(join, file.source).get("name") if join else None
            column = join_name or f"{member.name}Id"  # TypeORM default join column name
            target = _relation_target(relation, file.source)
            attrs = {
                "nullable": bool(options.get("nullable", True)),
                "unique": False,
                "primary_key": False,
                "references": tables.get(target, target),
            }
        else:
            return  # OneToMany etc. have no column in this table
        key = column_key(table, column)
        name = f"{cls.name}.{member.name}"
        result.nodes.append(self.node(ConceptKind.COLUMN, key, name, file, member.node, **attrs))


def _options(deco: Decorator | None, source: bytes) -> dict:
    """The options object, e.g. `@Column('text', { nullable: true })` -> {"nullable": True}."""
    if deco is None:
        return {}
    for arg in deco.args:
        value = literal(arg, source)
        if isinstance(value, dict):
            return value
    return {}


def _relation_target(deco: Decorator, source: bytes) -> str | None:
    """`@ManyToOne(() => User, ...)` -> "User"."""
    if not deco.args or deco.args[0].type != "arrow_function":
        return None
    return text(deco.args[0].child_by_field_name("body"), source)
