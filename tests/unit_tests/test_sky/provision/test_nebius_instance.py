"""Tests for Nebius provisioning waits."""

import textwrap
from typing import List
from unittest import mock

import pytest

from sky import skypilot_config
from sky.provision.nebius import instance


@pytest.fixture()
def load_config(tmp_path, monkeypatch):
    """Loads the given YAML as SkyPilot's global config for one test."""
    for name in (skypilot_config.ENV_VAR_SKYPILOT_CONFIG,
                 skypilot_config.ENV_VAR_GLOBAL_CONFIG,
                 skypilot_config.ENV_VAR_PROJECT_CONFIG):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(skypilot_config, '_PROJECT_CONFIG_PATH',
                        str(tmp_path / 'no-project-config.yaml'))

    def _load(content: str) -> None:
        config_file = tmp_path / 'config.yaml'
        config_file.write_text(content)
        with mock.patch.object(skypilot_config, '_GLOBAL_CONFIG_PATH',
                               str(config_file)):
            skypilot_config.reload_config()

    yield _load
    # The patches are gone by now, so this restores the user's real config.
    skypilot_config.reload_config()


def _wait(monkeypatch, pending_per_poll: List[List[str]],
          max_retries: int) -> int:
    """Runs _wait_until_no_pending over scripted pending sets; returns polls."""
    polls = iter(pending_per_poll)
    calls = []

    def fake_filter(*args, **kwargs):
        del args, kwargs
        ids = next(polls)
        calls.append(ids)
        return {i: {'status': 'STARTING'} for i in ids}

    monkeypatch.setattr(instance, '_filter_instances', fake_filter)
    monkeypatch.setattr(instance, '_max_retries_to_launch',
                        lambda _: max_retries)
    monkeypatch.setattr(instance, 'time', mock.Mock())
    instance._wait_until_no_pending('eu-north1', 'c', project_id='p')
    return len(calls)


def test_budget_defaults_to_120_polls(load_config):
    load_config('')
    assert instance._max_retries_to_launch('eu-north1') == 120


def test_provision_timeout_sets_the_budget_in_seconds(load_config):
    load_config('nebius:\n  provision_timeout: 30\n')
    # 30s of waiting, one poll every 5s.
    assert instance._max_retries_to_launch('eu-north1') == 6


def test_region_provision_timeout_overrides_the_cloud_level(load_config):
    load_config(
        textwrap.dedent("""\
            nebius:
              provision_timeout: 30
              region_configs:
                eu-north1:
                  provision_timeout: 60
            """))
    assert instance._max_retries_to_launch('eu-north1') == 12
    assert instance._max_retries_to_launch('eu-west1') == 6


def test_budget_shorter_than_one_poll_still_checks_once(load_config):
    load_config('nebius:\n  provision_timeout: 2\n')
    assert instance._max_retries_to_launch('eu-north1') == 1


def test_timeout_reports_the_configured_budget(monkeypatch, load_config):
    load_config('nebius:\n  provision_timeout: 10\n')
    monkeypatch.setattr(instance, '_filter_instances',
                        lambda *args, **kwargs: {'a': {
                            'status': 'STARTING'
                        }})
    monkeypatch.setattr(instance, 'time', mock.Mock())
    with pytest.raises(TimeoutError, match='for 10 seconds'):
        instance._wait_until_no_pending('eu-north1', 'c', project_id='p')


def test_steady_progress_outlasts_the_budget(monkeypatch):
    # Six nodes, one leaves STARTING every two polls: 13 polls in all, far
    # past a 3-poll budget, but never 3 polls in a row without progress.
    nodes = [f'i{n}' for n in range(6)]
    seq = []
    for remaining in range(6, 0, -1):
        seq += [nodes[:remaining]] * 2
    seq.append([])
    assert _wait(monkeypatch, seq, max_retries=3) == len(seq)


def test_times_out_without_progress(monkeypatch):
    with pytest.raises(TimeoutError, match='No instance left STARTING'):
        _wait(monkeypatch, [['a', 'b']] * 10, max_retries=3)


def test_a_newly_pending_instance_is_not_progress(monkeypatch):
    seq = [['a'], ['a', 'b'], ['a', 'b'], ['a', 'b'], ['a', 'b']]
    with pytest.raises(TimeoutError):
        _wait(monkeypatch, seq, max_retries=3)
