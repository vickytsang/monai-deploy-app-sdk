# Copyright 2020 - 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import inspect
import runpy
import sys
import warnings
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple, Union

import pkg_resources

if TYPE_CHECKING:
    from monai.deploy.core import Application


def get_docstring(cls: type) -> str:
    """Get docstring of a class.

    Tries to get docstring from class itself, from its __doc__.
    It trims the preceeding whitespace from docstring.
    If __doc__ is not available, it returns empty string.

    Args:
        cls (type): class to get docstring from.

    Returns:
        A docstring of the class.
    """
    doc = cls.__doc__
    if doc is None:
        return ""
    # Trim white-space for each line in the string
    return "\n".join([line.strip() for line in doc.split("\n")])


def is_application(cls: Any) -> bool:
    """Check if the given type is a subclass of Application class."""
    if hasattr(cls, "_class_id") and cls._class_id == "monai.application":
        if inspect.isclass(cls) and hasattr(cls, "__abstractmethods__") and len(cls.__abstractmethods__) != 0:
            return False
        return True
    return False


def get_application(path: Union[str, Path]) -> Optional[Application]:
    """Get application object from path."""

    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist")

    # Setup PYTHONPATH if the target path is a file
    if path.is_file() and sys.path[0] != str(path.parent):
        sys.path.insert(0, str(path.parent))

    # Execute the module with runpy (`run_name` would be '<run_path>' by default.)
    vars = runpy.run_path(str(path))

    # Get the Application class from the module and return an instance of it
    for var in vars.keys():
        if not var.startswith("_"):  # skip private variables
            app_cls = vars[var]
            if is_application(app_cls):
                # Create Application object with the application path
                app_obj = app_cls(do_run=False, path=path)
                return app_obj
    return None


def get_class_file_path(cls) -> Path:
    """Get the file path of a class."""
    return Path(inspect.getfile(cls))


######################################################################################
# The following implementations are borrowed from `monai.utils.module` of MONAI Core.
######################################################################################

OPTIONAL_IMPORT_MSG_FMT = "{}"


class OptionalImportError(ImportError):
    """Raises when an optional dependency could not be imported."""


def min_version(the_module, min_version_str: str = "") -> bool:
    """
    Convert version strings into tuples of int and compare them.

    Returns True if the module's version is greater or equal to the 'min_version'.
    When min_version_str is not provided, it always returns True.
    """
    if not min_version_str or not hasattr(the_module, "__version__"):
        return True  # always valid version

    mod_version = tuple(int(x) for x in the_module.__version__.split(".")[:2])
    required = tuple(int(x) for x in min_version_str.split(".")[:2])
    return mod_version >= required


def exact_version(the_module, version_str: str = "") -> bool:
    """
    Returns True if the module's __version__ matches version_str
    """
    if not hasattr(the_module, "__version__"):
        warnings.warn(f"{the_module} has no attribute __version__ in exact_version check.")
        return False
    return bool(the_module.__version__ == version_str)


def optional_import(
    module: str,
    version: str = "",
    version_checker: Callable[..., bool] = min_version,
    name: str = "",
    descriptor: str = OPTIONAL_IMPORT_MSG_FMT,
    version_args=None,
    allow_namespace_pkg: bool = False,
) -> Tuple[Any, bool]:
    """
    Imports an optional module specified by `module` string.
    Any importing related exceptions will be stored, and exceptions raise lazily
    when attempting to use the failed-to-import module.

    Args:
        module: name of the module to be imported.
        version: version string used by the version_checker.
        version_checker: a callable to check the module version, Defaults to monai.utils.min_version.
        name: a non-module attribute (such as method/class) to import from the imported module.
        descriptor: a format string for the final error message when using a not imported module.
        version_args: additional parameters to the version checker.
        allow_namespace_pkg: whether importing a namespace package is allowed. Defaults to False.

    Returns:
        The imported module and a boolean flag indicating whether the import is successful.

    Examples::

        >>> torch, flag = optional_import('torch', '1.1')
        >>> print(torch, flag)
        <module 'torch' from 'python/lib/python3.6/site-packages/torch/__init__.py'> True

        >>> the_module, flag = optional_import('unknown_module')
        >>> print(flag)
        False
        >>> the_module.method  # trying to access a module which is not imported
        OptionalImportError: import unknown_module (No module named 'unknown_module').

        >>> torch, flag = optional_import('torch', '42', exact_version)
        >>> torch.nn  # trying to access a module for which there isn't a proper version imported
        OptionalImportError: import torch (requires version '42' by 'exact_version').

        >>> conv, flag = optional_import('torch.nn.functional', '1.0', name='conv1d')
        >>> print(conv)
        <built-in method conv1d of type object at 0x11a49eac0>

        >>> conv, flag = optional_import('torch.nn.functional', '42', name='conv1d')
        >>> conv()  # trying to use a function from the not successfully imported module (due to unmatched version)
        OptionalImportError: from torch.nn.functional import conv1d (requires version '42' by 'min_version').
    """

    tb = None
    exception_str = ""
    if name:
        actual_cmd = f"from {module} import {name}"
    else:
        actual_cmd = f"import {module}"
    try:
        pkg = __import__(module)  # top level module
        the_module = import_module(module)
        if not allow_namespace_pkg:
            is_namespace = getattr(the_module, "__file__", None) is None and hasattr(the_module, "__path__")
            if is_namespace:
                raise AssertionError
        if name:  # user specified to load class/function/... from the module
            the_module = getattr(the_module, name)
    except Exception as import_exception:  # any exceptions during import
        tb = import_exception.__traceback__
        exception_str = f"{import_exception}"
    else:  # found the module
        if version_args and version_checker(pkg, f"{version}", version_args):
            return the_module, True
        if not version_args and version_checker(pkg, f"{version}"):
            return the_module, True

    # preparing lazy error message
    msg = descriptor.format(actual_cmd)
    if version and tb is None:  # a pure version issue
        msg += f" (requires '{module} {version}' by '{version_checker.__name__}')"
    if exception_str:
        msg += f" ({exception_str})"

    class _LazyRaise:
        def __init__(self, *_args, **_kwargs):
            _default_msg = (
                f"{msg}."
                + "\n\nFor details about installing the optional dependencies, please visit:"
                + "\n    https://docs.monai.io/en/latest/installation.html#installing-the-recommended-dependencies"
            )
            if tb is None:
                self._exception = OptionalImportError(_default_msg)
            else:
                self._exception = OptionalImportError(_default_msg).with_traceback(tb)

        def __getattr__(self, name):
            """
            Raises:
                OptionalImportError: When you call this method.
            """
            raise self._exception

        def __call__(self, *_args, **_kwargs):
            """
            Raises:
                OptionalImportError: When you call this method.
            """
            raise self._exception

    return _LazyRaise(), False


######################################################################################


def is_dist_editable(project_name: str) -> bool:
    distributions: Dict = {v.key: v for v in pkg_resources.working_set}
    dist: Any = distributions.get(project_name)
    if not hasattr(dist, "egg_info"):
        return False
    egg_info = Path(dist.egg_info)
    if egg_info.is_dir() and egg_info.suffix == ".egg-info":
        return True
    return False


def dist_module_path(project_name: str) -> str:
    distributions: Dict = {v.key: v for v in pkg_resources.working_set}
    dist: Any = distributions.get(project_name)
    if hasattr(dist, "module_path"):
        return str(dist.module_path)
    return ""


if __name__ == "__main__":
    argv = sys.argv
    if len(argv) == 3 and argv[1] == "is_dist_editable":
        if is_dist_editable(argv[2]):
            sys.exit(0)
        else:
            sys.exit(1)
    if len(argv) == 3 and argv[1] == "dist_module_path":
        module_path = dist_module_path(argv[2])
        if module_path:
            print(module_path)
            sys.exit(0)
        else:
            sys.exit(1)
