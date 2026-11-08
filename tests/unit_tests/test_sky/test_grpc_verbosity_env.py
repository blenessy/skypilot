"""Tests the GRPC_VERBOSITY default applied when the sky package is imported.

gRPC reads the variable once at import, so the value can only be observed in a
fresh interpreter: the parent pytest process may already have imported grpc.
"""
import os
import subprocess
import sys

_MARKER = 'GRPC_VERBOSITY='


def _grpc_verbosity_after_import(env_overrides):
    env = dict(os.environ)
    env.pop('GRPC_VERBOSITY', None)
    # The test suite sets SKYPILOT_DEBUG globally; start from its absence.
    env.pop('SKYPILOT_DEBUG', None)
    env.update(env_overrides)
    # SKYPILOT_DEBUG turns on SkyPilot's debug logging, which writes to stdout,
    # so the value is tagged and read back from the marker line.
    script = ('import os, sky; '
              f'print("{_MARKER}" + os.environ.get("GRPC_VERBOSITY", ""))')
    result = subprocess.run([sys.executable, '-c', script],
                            check=True,
                            capture_output=True,
                            env=env,
                            text=True)
    for line in result.stdout.splitlines():
        if line.startswith(_MARKER):
            return line[len(_MARKER):]
    raise AssertionError(f'{_MARKER} not printed: {result.stdout!r}')


class TestGrpcVerbosityDefault:

    def test_default_is_none(self):
        assert _grpc_verbosity_after_import({}) == 'NONE'

    def test_debug_keeps_grpc_logging_enabled(self):
        assert _grpc_verbosity_after_import({'SKYPILOT_DEBUG': '1'}) == ''

    def test_explicit_value_is_respected(self):
        env = {'GRPC_VERBOSITY': 'DEBUG'}
        assert _grpc_verbosity_after_import(env) == 'DEBUG'
