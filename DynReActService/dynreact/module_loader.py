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
    for importer in sys.meta_path + [importlib.util]:
        try:
            spec_res = importer.find_spec(module)
            mod = importlib.util.module_from_spec(spec_res)
            spec_res.loader.exec_module(mod)
            yield mod
        except GeneratorExit:
            raise
        except:
            continue


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
    mod0 = sys.modules.get(module)
    mod_set = mod0 is not None
    mod_iterator = iter([mod0]) if mod_set else iter_module_variants(module)
    _fallback_creates = []  # TODO tbd

    for mod in mod_iterator:
        for name, element in inspect.getmembers(mod):
            try:
                if inspect.isclass(element) and issubclass(element, clzz) and element != clzz:
                    result = element(*args, **kwargs)
                    if not mod_set:
                        sys.modules[module] = mod
                    return result
                elif (name == "create" or name == "create_provider") and inspect.isfunction(element):
                    _fallback_creates.append(element)
            except Exception as exc:
                if not isinstance(exc, ignored_exceptions):
                    errors.append(exc)
    if len(_fallback_creates) > 0:
        return _fallback_creates[0](*args, **kwargs)
    if len(errors) > 0:
        raise errors[0]
    if do_raise:
        raise Exception(f"Module {module} not found")
    return None
