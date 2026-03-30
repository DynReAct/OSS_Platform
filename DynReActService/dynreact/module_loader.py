import importlib.util
import inspect
import sys
from collections.abc import Iterator
from typing import Any


def iter_module_variants(module: str) -> Iterator[Any]:
    """
    Yield module candidates using the tolerant resolution strategy that was
    previously implemented directly in plugins.py.
    """
    mod0 = sys.modules.get(module)
    if mod0 is not None:
        yield mod0
        return

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

        if spec_res is None or spec_res.loader is None:
            continue

        mod = importlib.util.module_from_spec(spec_res)
        spec_res.loader.exec_module(mod)
        yield mod


def import_module(module: str) -> Any:
    """
    Import a module through the tolerant namespace-aware resolution strategy.
    """
    mod0 = sys.modules.get(module)
    if mod0 is not None:
        return mod0

    for mod in iter_module_variants(module):
        sys.modules[module] = mod
        return mod

    raise ImportError(f"Module {module} not found")


def instantiate_first_matching(
    module: str,
    clzz,
    *args,
    do_raise: bool = False,
    ignored_exceptions: tuple[type[Exception], ...] = (),
    **kwargs,
) -> Any | None:
    """
    Instantiate the first discovered subclass of ``clzz`` in the resolved
    module, preserving the historical behavior from plugins.py.
    """
    if len(args) > 0 and isinstance(args[0], str) and args[0].startswith("class:"):
        first = args[0]
        module = first[first.index(":") + 1:first.index(",")]
        first = first[first.index(",") + 1:]
        args = tuple(a if idx > 0 else first for idx, a in enumerate(args))

    errors: list[Exception] = []
    mod0 = sys.modules.get(module)
    mod_set = mod0 is not None
    mod_iterator = iter([mod0]) if mod_set else iter_module_variants(module)

    for mod in mod_iterator:
        for _, element in inspect.getmembers(mod):
            try:
                if inspect.isclass(element) and issubclass(element, clzz) and element != clzz:
                    result = element(*args, **kwargs)
                    if not mod_set:
                        sys.modules[module] = mod
                    return result
            except Exception as exc:
                if not isinstance(exc, ignored_exceptions):
                    errors.append(exc)
                    if do_raise:
                        raise

    if len(errors) > 0:
        raise errors[0]
    if do_raise:
        raise Exception(f"Module {module} not found")
    return None
