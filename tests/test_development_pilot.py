import json
from pathlib import Path
from unittest.mock import Mock

from governance.evaluation import main, summarize_trials, validate_freeze
from governance.source import DemoSource, MySQLSource
from tests.test_evaluation import MANIFEST, trial
from tests.test_providers import EmptyGemini


def setup_pilot(tmp_path, monkeypatch):
    # Dotenv must not replace the deliberately absent credential in these tests.
    monkeypatch.setenv('LLM_PROVIDER', 'gemini')
    monkeypatch.setenv('GEMINI_MODEL', 'test-gemini')
    monkeypatch.setenv('GEMINI_API_KEY', 'TEST_ONLY')
    source = DemoSource()
    source.close = Mock()
    monkeypatch.setattr(MySQLSource, 'from_env', staticmethod(lambda: source))
    budgets = tmp_path / 'budgets.json'
    budgets.write_text(json.dumps({'max_calls': 100, 'max_tokens': 64000}))
    argv = ['pilot', 'C', str(tmp_path / 'output'), '--budgets', str(budgets)]
    return source, argv


def test_development_pilot_records_originals_and_effective_limits(tmp_path, monkeypatch, capsys):
    source, argv = setup_pilot(tmp_path, monkeypatch)
    monkeypatch.setattr('governance.providers.create_client', lambda: EmptyGemini())
    assert main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(result['artifact']).read_text(encoding='utf-8'))
    assert artifact['split'] == 'development'
    assert artifact['status'] == 'development_completed'
    assert artifact['limits']['max_calls'] == 100
    assert artifact['limits']['max_retries'] == 1
    assert artifact['original_proposals'] == []
    assert artifact['privacy']['raw_values_allowed'] is False
    assert 'manifest_hash' not in artifact
    source.close.assert_called_once()


def test_check_only_never_creates_provider_or_artifact(tmp_path, monkeypatch, capsys):
    source, argv = setup_pilot(tmp_path, monkeypatch)
    factory = Mock(side_effect=AssertionError('No provider in check-only'))
    monkeypatch.setattr('governance.providers.create_client', factory)
    assert main(argv + ['--check-only']) == 0
    assert json.loads(capsys.readouterr().out)['preflight']['ready'] is True
    assert not (tmp_path / 'output').exists()
    factory.assert_not_called()
    source.close.assert_called_once()


def test_missing_key_is_actionable_and_does_not_start_pilot(tmp_path, monkeypatch, capsys):
    source, argv = setup_pilot(tmp_path, monkeypatch)
    monkeypatch.setenv('GEMINI_API_KEY', '')
    factory = Mock(side_effect=AssertionError('No provider without credentials'))
    monkeypatch.setattr('governance.providers.create_client', factory)
    assert main(argv) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'pending'
    assert result['preflight']['issues'][0]['code'] == 'provider_configuration'
    assert not (tmp_path / 'output').exists()
    factory.assert_not_called()
    source.close.assert_called_once()


def test_development_runs_cannot_enter_final_even_with_matching_fields():
    runs = [trial(approach, approach + str(i)) for approach in ('B', 'C') for i in range(3)]
    for run in runs:
        run['split'] = 'development'
    assert validate_freeze(MANIFEST, runs)['eligible_trials'] == {'B': 0, 'C': 0}
    assert summarize_trials(runs)['approaches'] == {}


def test_exhausted_pilot_keeps_artifact_and_returns_failure(tmp_path, monkeypatch, capsys):
    source, argv = setup_pilot(tmp_path, monkeypatch)
    (tmp_path / 'budgets.json').write_text(json.dumps({'max_tokens': 1}))
    monkeypatch.setattr('governance.providers.create_client', lambda: EmptyGemini())
    assert main(argv) == 2
    result = json.loads(capsys.readouterr().out)
    artifact = json.loads(Path(result['artifact']).read_text(encoding='utf-8'))
    assert artifact['status'] == 'failed'
    assert artifact['inspection_status'] == 'budget_exhausted'
    assert artifact['usage']['requests'] == 0
    source.close.assert_called_once()


def test_missing_mysql_returns_actionable_pending_without_provider(tmp_path, monkeypatch, capsys):
    _, argv = setup_pilot(tmp_path, monkeypatch)
    monkeypatch.setattr(
        MySQLSource, 'from_env', Mock(side_effect=ValueError('PRIVATE_CONNECTION_SECRET'))
    )
    factory = Mock(side_effect=AssertionError('No model without a source'))
    monkeypatch.setattr('governance.providers.create_client', factory)
    assert main(argv + ['--check-only']) == 2
    text = capsys.readouterr().out
    result = json.loads(text)
    assert result['status'] == 'pending'
    assert result['preflight']['issues'][0]['code'] == 'source_connection'
    assert 'MYSQL_' in result['preflight']['issues'][0]['message']
    assert 'PRIVATE_CONNECTION_SECRET' not in text
    factory.assert_not_called()
