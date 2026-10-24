"""Analysis modules. Importing this package imports every file here, so a new file = a new module."""

import importlib
import pkgutil

for _m in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_m.name}")
