import importlib.util
import inspect
import pkgutil
import sys
from collections.abc import Iterator
from typing import Any


def _find_spec(module: str):
    for importer in sys.meta_path + [importlib.util]:
        find_spec = getattr(importer, "find_spec", None)
        if find_spec is None:
            continue
        try:
            spec_res = find_spec(module, path=None)
        except TypeError:
            try:
                spec_res = find_spec(module)
            except Exception:
                continue
        except Exception:
            continue
        if spec_res is not None:
            return spec_res
    return None


def module_exists(module: str) -> bool:
    return module in sys.modules or _find_spec(module) is not None


def resolve_explicit_reference(reference: str) -> tuple[str, str | None]:
    """
    Resolve an explicit ``class:...`` reference.

    The reference can point either to a module (historical behavior) or to a
    concrete class using a dotted path such as ``dynreact.custom.MyProvider``.
    """
    if module_exists(reference):
        return reference, None
    if "." not in reference:
        return reference, None
    module_name, class_name = reference.rsplit(".", 1)
    return module_name, class_name


def iter_module_variants(module: str) -> Iterator[Any]:
    """
    Yield module candidates using the tolerant resolution strategy that was
    previously implemented directly in plugins.py.
    """
    mod0 = sys.modules.get(module)
    if mod0 is not None:
        yield mod0
        return

    spec_res = _find_spec(module)
    if spec_res is None or spec_res.loader is None:
        return

    mod = importlib.util.module_from_spec(spec_res)
    spec_res.loader.exec_module(mod)
    yield mod


def iter_matching_modules(module: str) -> Iterator[Any]:
    seen: set[str] = set()
    for mod in iter_module_variants(module):
        name = getattr(mod, "__name__", module)
        seen.add(name)
        yield mod

        for loaded_name, loaded_mod in tuple(sys.modules.items()):
            if loaded_mod is None or not loaded_name.startswith(f"{module}.") or loaded_name in seen:
                continue
            seen.add(loaded_name)
            yield loaded_mod

        mod_path = getattr(mod, "__path__", None)
        if mod_path is None:
            continue
        for child in pkgutil.iter_modules(mod_path, prefix=f"{module}."):
            if child.name in seen:
                continue
            for child_mod in iter_module_variants(child.name):
                child_name = getattr(child_mod, "__name__", child.name)
                if child_name in seen:
                    continue
                seen.add(child_name)
                yield child_mod


def instantiate_first_matching(
    module: str,
    clzz,
    *args,
    explicit_class_name: str | None = None,
    do_raise: bool = False,
    ignored_exceptions: tuple[type[Exception], ...] = (),
    **kwargs,
) -> Any | None:
    """
    Instantiate the first discovered subclass of ``clzz`` in the resolved
    module, preserving the historical behavior from plugins.py.
    Parameters:
        module: can be full path (incl. file name w/o .py ending) or a pure package path
        clzz: required interface/superclass
        args:
        do_raise:
        ignored_exceptions:
        kwargs:

    Returns:
         A class instance
    """
    errors: list[Exception] = []
    mod_iterator = iter_matching_modules(module)
    for mod in mod_iterator:
        members = inspect.getmembers(mod)
        if explicit_class_name is not None:
            element = getattr(mod, explicit_class_name, None)
            members = [(explicit_class_name, element)] if element is not None else []
        for name, element in members:
            try:
                if inspect.isclass(element) and issubclass(element, clzz) and element != clzz:
                    result = element(*args, **kwargs)
                    sys.modules[module] = mod
                    return result
            except Exception as exc:
                if not isinstance(exc, ignored_exceptions):
                    errors.append(exc)
    if len(errors) > 0:
        raise errors[0]
    if do_raise:
        suffix = f", class {explicit_class_name}" if explicit_class_name is not None else ""
        raise Exception(f"Module {module}{suffix} not found")
    return None
