from migrator.adapters.frameworks import FrameworkAdapter, load_files
from migrator.adapters.languages import PythonAdapter, TypeScriptAdapter
from migrator.concepts.models import ConceptKind
from migrator.repository import LocalRepository


def extract(make_repo, adapter: FrameworkAdapter, files: dict[str, str]):
    root = make_repo(files)
    language = TypeScriptAdapter() if adapter.language == "typescript" else PythonAdapter()
    return adapter.extract(load_files(LocalRepository(root), sorted(files), language))


def by_key(extraction, kind: ConceptKind) -> dict:
    return {n.key: n.attributes for n in extraction.nodes if n.kind == kind}
