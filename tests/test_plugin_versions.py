import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sdk.base_plugin import BasePlugin
from core.plugin_manager import PluginManager, plugin_version
from core.plugin_metadata import installed_plugin_version


def test_installed_version_reader_does_not_execute_plugin(tmp_path):
    path = tmp_path / 'main.py'
    path.write_text('raise RuntimeError("must not run")\nclass Plugin(BasePlugin):\n    VERSION = "2.1.3"\n', encoding='utf-8')
    assert installed_plugin_version(path) == '2.1.3'


@pytest.mark.parametrize('source', ['broken syntax !', 'class Plugin(BasePlugin):\n    VERSION = "bad"',
                                  'class Plugin(BasePlugin):\n    pass'])
def test_unreadable_or_invalid_installed_version_is_unknown(tmp_path, source):
    path = tmp_path / 'main.py'
    path.write_text(source, encoding='utf-8')
    assert installed_plugin_version(path) is None
    assert installed_plugin_version(tmp_path / 'missing.py') is None


def test_all_builtin_plugins_declare_valid_independent_versions():
    root = Path(__file__).resolve().parents[1] / 'plugins'
    paths = sorted(root.glob('*/main.py'))
    assert len(paths) == 12
    for path in paths:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)
                   and any(isinstance(base, ast.Name) and base.id == 'BasePlugin'
                           for base in node.bases)]
        assert len(classes) == 1, path
        versions = [node.value.value for node in classes[0].body
                    if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'VERSION'
                            for target in node.targets)
                    and isinstance(node.value, ast.Constant)]
        assert len(versions) == 1, path
        assert plugin_version(SimpleNamespace(VERSION=versions[0])) == versions[0]
        assert ast.get_docstring(classes[0]), path


@pytest.mark.parametrize('value', ['', '1.2', '01.2.3', '1.2.3.4', None, 1])
def test_invalid_version_is_rejected(value):
    with pytest.raises(ValueError, match='MAJOR.MINOR.PATCH'):
        plugin_version(SimpleNamespace(VERSION=value))


def test_legacy_extension_has_explicit_unversioned_fallback():
    assert plugin_version(BasePlugin) == '0.0.0'


def test_discovery_publishes_loaded_versions_and_does_not_start_disabled_plugins(monkeypatch):
    engine = SimpleNamespace(settings={'plugins': {'disabled': False}},
                             shared_state=Mock())
    manager = PluginManager(engine)
    manager.plugin_dir = 'synthetic-plugin-root'
    monkeypatch.setattr('core.plugin_manager.os.path.isdir', lambda _: True)
    monkeypatch.setattr('core.plugin_manager.os.path.exists', lambda _: True)
    monkeypatch.setattr('core.plugin_manager.os.listdir', lambda _: ['enabled', 'disabled'])
    manager._find_plugin_class = Mock(return_value=type('Example', (BasePlugin,), {'VERSION': '2.3.4'}))
    manager._spawn = Mock()
    manager.discover_and_load()
    manager._find_plugin_class.assert_called_once_with('enabled')
    manager._spawn.assert_called_once_with('enabled')
    assert manager.plugins['enabled']['version'] == '2.3.4'
    engine.shared_state.set.assert_called_once_with('plugin_versions', {'enabled': '2.3.4'})
