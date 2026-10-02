"""Read installed plugin release metadata without importing plugin code."""
import ast
from pathlib import Path
import re


def installed_plugin_version(path):
    """Return a declared version, including for disabled plugins; fail visibly."""
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8-sig"))
        versions = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(isinstance(base, ast.Name) and base.id == "BasePlugin"
                       for base in node.bases):
                continue
            for entry in node.body:
                if isinstance(entry, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "VERSION"
                        for target in entry.targets):
                    versions.append(ast.literal_eval(entry.value))
        if len(versions) == 1 and isinstance(versions[0], str) and re.fullmatch(
                r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", versions[0]):
            return versions[0]
    except (OSError, SyntaxError, ValueError, TypeError):
        pass
    return None
