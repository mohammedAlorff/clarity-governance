"""Provider imports must not load the inspection engine or HTTP application."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('module', ['openai', 'gemini', 'local'])
def test_provider_can_load_without_application_or_agent(module):
    code = f"""
import importlib
import sys
module = importlib.import_module('governance.providers.{module}')
assert 'governance.agent' not in sys.modules
assert 'governance.app' not in sys.modules
assert 'governance.store' not in sys.modules
client_type = (module.OpenAIClient if '{module}' == 'openai' else
               module.GeminiClient if '{module}' == 'gemini' else module.LocalChatClient)
client = (client_type(api_key='offline-construction-only', model='test')
          if '{module}' != 'local' else client_type(model='test'))
assert client.provider == '{module}'
"""
    result = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_installed_app_finds_assets_and_project_root_from_another_directory(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    code = """
from pathlib import Path
import sys
import governance
from fastapi.testclient import TestClient
from governance.app import ROOT, STATIC, create_app
expected = Path(sys.argv[1]).resolve()
assert Path(governance.__file__).resolve().parent == expected / 'src' / 'governance'
assert ROOT == expected
assert STATIC == expected / 'src' / 'governance' / 'static'
with TestClient(create_app(str(Path.cwd() / 'assets.db'))) as client:
    assert client.get('/').status_code == 200
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
"""
    result = subprocess.run(
        [sys.executable, '-c', code, str(project_root)],
        cwd=tmp_path,
        env={**os.environ, 'GOVERNANCE_DB': str(tmp_path / 'app.db')},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
