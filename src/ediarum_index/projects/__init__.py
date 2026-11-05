"""Project registry, auto-discovered from the modules in this package.

Each module (``projects/<module>.py`` or a package ``projects/<module>/``) defines ``NAME`` (the platform's project slug;
the module is named after it, with "-" spelled "_"), optional
``LABEL`` / ``DESCRIPTION`` / ``REGISTER_DIR``, optional ``ENTRY_TYPES`` (the
entry types it uses — its tabs; all of ``models.ENTRY_TYPES`` without it) and
optional ``OVERRIDES`` (``{entry_type: SchemaOverride}``). Underscore-prefixed files (``_template.py``) are skipped.

Exports consumed elsewhere:
  * ``PROJECT_NAMES``     — used by ``schemas.resolve_schema``
  * ``PROJECT_OVERRIDES`` — ``{(project, entry_type): SchemaOverride}``
  * ``PROJECT_ENTRY_TYPES`` — ``{project: (entry_type, ...)}`` for the modules
    that declare ``ENTRY_TYPES``; read through ``schemas.entry_types_for``
  * ``PROJECT_MODULES``   — ``{project_name: module}``; ``sources.py`` reads a
    project's optional ``REGISTER_DIR`` from it (where its registers are in
    its repository; a project without one isn't ingested from XML)
  * ``iter_projects()``   — seed source for ``bootstrap.sync_registry``
  * ``SCHEMA_VERSION``    — bump to invalidate the ``resolve_schema`` cache

Adding a module changes behaviour on the next restart only (no reload).
"""

import importlib
import pkgutil

from ..models import ENTRY_TYPES, SchemaOverride

SCHEMA_VERSION = 8  # bumped: avhr drops `internal_id` (its xml:id is the source_id)

# discover every non-underscore module in this package once, keep the module objects
_MODULES = [
    importlib.import_module(f"{__name__}.{m.name}")
    for m in pkgutil.iter_modules(__path__)
    if not m.name.startswith("_")
]

PROJECT_NAMES: list[str] = [m.NAME for m in _MODULES]

PROJECT_MODULES = {m.NAME: m for m in _MODULES}

PROJECT_OVERRIDES: dict[tuple[str, str], SchemaOverride] = {
    (m.NAME, etype): ov
    for m in _MODULES
    for etype, ov in getattr(m, "OVERRIDES", {}).items()
}



def _declared_entry_types(module) -> tuple[str, ...] | None:
    """``module.ENTRY_TYPES``, checked: every name a known entry type, and every
    ``OVERRIDES`` key among them (an override for a type the project doesn't
    use is a typo or drift). None if the module doesn't declare it."""
    declared = getattr(module, "ENTRY_TYPES", None)
    if declared is None:
        return None
    known = {name for name, _ in ENTRY_TYPES}
    if unknown := [t for t in declared if t not in known]:
        raise ValueError(f"project {module.NAME!r}: unknown ENTRY_TYPES {unknown}")
    if stray := sorted(set(getattr(module, "OVERRIDES", {})) - set(declared)):
        raise ValueError(f"project {module.NAME!r}: OVERRIDES for types not in ENTRY_TYPES: {stray}")
    return tuple(declared)


PROJECT_ENTRY_TYPES: dict[str, tuple[str, ...]] = {
    m.NAME: declared
    for m in _MODULES
    if (declared := _declared_entry_types(m)) is not None
}


def iter_projects():
    """Yield (name, label, description) for every discovered project module."""
    for m in _MODULES:
        yield m.NAME, getattr(m, "LABEL", m.NAME), getattr(m, "DESCRIPTION", None)
