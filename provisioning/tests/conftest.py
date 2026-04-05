from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def unload_alias(alias: str) -> None:
    for name in list(sys.modules):
        if name == alias or name.startswith(f"{alias}."):
            del sys.modules[name]


def load_service_module(service_dir: str, alias: str, module_name: str, reload_package: bool = False):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    if reload_package or alias not in sys.modules:
        unload_alias(alias)
        package_dir = ROOT / service_dir / "app"
        init_file = package_dir / "__init__.py"
        spec = importlib.util.spec_from_file_location(
            alias,
            init_file,
            submodule_search_locations=[str(package_dir)],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load package alias {alias}")

        package = importlib.util.module_from_spec(spec)
        sys.modules[alias] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f"{alias}.{module_name}")
