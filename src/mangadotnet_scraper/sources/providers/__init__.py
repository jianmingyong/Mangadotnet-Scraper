import importlib
import pkgutil

for item in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{item.name}")
