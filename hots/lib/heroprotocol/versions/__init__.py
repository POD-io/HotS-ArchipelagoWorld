#!/usr/bin/env python
#
# Copyright 2015-2020 Blizzard Entertainment. Subject to the MIT license.
# See the included LICENSE file for more information.
#
import importlib
import importlib.util
import os
import re
import sys


def _in_apworld_zip() -> bool:
    module_file = globals().get("__file__", "")
    return ".apworld" in module_file.replace("/", os.sep).lower()


def _zip_paths():
    module_file = globals()["__file__"].replace("/", os.sep)
    idx = module_file.lower().index(".apworld")
    zip_path = module_file[: idx + len(".apworld")]
    inner = module_file[idx + len(".apworld") :].lstrip("\\/").replace("\\", "/")
    inner_dir = os.path.dirname(inner).replace("\\", "/")
    return zip_path, inner_dir


def _import_protocol(base_path, protocol_module_name):
    """Import a protocol module from base_path (loose files or .apworld zip)."""
    if protocol_module_name in sys.modules:
        return sys.modules[protocol_module_name]

    if _in_apworld_zip():
        return importlib.import_module(f"heroprotocol.versions.{protocol_module_name}")

    module_path = os.path.join(base_path, protocol_module_name + ".py")
    spec = importlib.util.spec_from_file_location(protocol_module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load protocol module {protocol_module_name!r} from {base_path!r}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[protocol_module_name] = module
    spec.loader.exec_module(module)
    return module


def list_all(base_path=None):
    """Return protocol version filenames sorted by name."""
    if base_path is None:
        base_path = os.path.dirname(__file__)
    pattern = re.compile(r"protocol[0-9]+\.py$")
    try:
        files = sorted(f for f in os.listdir(base_path) if pattern.match(f))
        if files:
            return files
    except (FileNotFoundError, OSError):
        pass

    if _in_apworld_zip():
        import zipfile

        zip_path, inner_dir = _zip_paths()
        with zipfile.ZipFile(zip_path) as zf:
            files = sorted(
                os.path.basename(name)
                for name in zf.namelist()
                if name.startswith(inner_dir) and pattern.match(os.path.basename(name))
            )
            if files:
                return files

    return ["protocol96477.py"]


def latest():
    """Import the latest bundled protocol version."""
    base_path = os.path.dirname(__file__)
    files = list_all(base_path)
    module_name = files[-1].split(".")[0]
    return _import_protocol(base_path, module_name)


def build(build_version):
    """Get the module for a specific build version."""
    base_path = os.path.dirname(__file__)
    return _import_protocol(base_path, "protocol{0:05d}".format(build_version))
