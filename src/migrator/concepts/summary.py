"""Human readable view of a concept model: the API and database surface of an app."""

from migrator.concepts.models import ConceptKind, ConceptModel


def format_concepts(model: ConceptModel) -> str:
    out = [f"Concepts for {model.repo} (frameworks: {', '.join(model.frameworks) or 'none'})", ""]

    out.append("API routes:")
    for route in model.of_kind(ConceptKind.ROUTE):
        a = route.attributes
        auth = "auth" if a["auth"] else "open"
        body = f"  body={a['body']}" if a.get("body") else ""
        out.append(
            f"  {a['method']:<7} {a['path']:<28} -> {a['status']}  {auth}{body}  ({route.name})"
        )

    out.append("\nRequest fields:")
    for field in model.of_kind(ConceptKind.INPUT_FIELD):
        need = "required" if field.attributes["required"] else "optional"
        rules = ", ".join(field.attributes["constraints"]) or "-"
        out.append(f"  {field.key:<40} {need:<9} {rules}")

    out.append("\nDatabase:")
    for table in model.of_kind(ConceptKind.TABLE):
        out.append(f"  {table.key} ({table.name})")
        for column in model.of_kind(ConceptKind.COLUMN):
            if column.key.startswith(table.key + "."):
                out.append(
                    f"    {column.key.split('.', 1)[1]:<16} {_column_flags(column.attributes)}"
                )

    errors = sorted({n.attributes["status"] for n in model.of_kind(ConceptKind.ERROR)})
    out.append(f"\nErrors raised on purpose: {', '.join(map(str, errors)) or 'none'}")
    env = [n.key for n in model.of_kind(ConceptKind.ENV_VAR)]
    out.append(f"Env vars: {', '.join(env) or 'none'}")
    providers = [n.name for n in model.of_kind(ConceptKind.PROVIDER)]
    if providers:
        out.append(f"Providers: {', '.join(providers)}")
    out.extend(f"Note: {note}" for note in model.notes)
    return "\n".join(out)


def _column_flags(attrs: dict) -> str:
    flags = [
        "primary key" if attrs["primary_key"] else ("null" if attrs["nullable"] else "not null")
    ]
    if attrs["unique"]:
        flags.append("unique")
    if attrs.get("references"):
        flags.append(f"-> {attrs['references']}")
    return ", ".join(flags)
