"""公开版本的远程选择与配置传递回归。"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from local_knowledge_agent import cli


def remote_runner(command):
    remotes = {'origin': 'https://public.example.net/team/repo.git',
               'preferred': 'https://code.example.test/team/repo.git',
               'aaa-spoofed': 'https://evil-example.test/team/repo.git'}
    output = '\n'.join(remotes) if command[-1] == 'remote' else remotes[command[-1]]
    return subprocess.CompletedProcess(command, 0, output, '')


class RemotePreferenceTests(unittest.TestCase):
    def test_default_origin_and_explicit_hostname_boundary(self):
        self.assertEqual(cli.select_repository_remote(Path('.'), runner=remote_runner)['remote_name'], 'origin')
        result = cli.select_repository_remote(Path('.'), runner=remote_runner, preferred_remote_hosts=['example.test'])
        self.assertEqual(result['remote_name'], 'preferred')
        result = cli.select_repository_remote(Path('.'), runner=remote_runner, preferred_remote_hosts=['CODE.EXAMPLE.TEST'])
        self.assertEqual(result['remote_name'], 'preferred')
        result = cli.select_repository_remote(Path('.'), runner=remote_runner, preferred_remote_hosts=['missing.test'])
        self.assertEqual(result['remote_name'], 'origin')

    def test_no_implicit_github_preference(self):
        def runner(command):
            remotes = {'origin': 'https://gitlab.example.test/team/repo.git',
                       'upstream': 'git@github.com:example/repo.git'}
            output = '\n'.join(remotes) if command[-1] == 'remote' else remotes[command[-1]]
            return subprocess.CompletedProcess(command, 0, output, '')
        self.assertEqual(cli.select_repository_remote(Path('.'), runner=runner)['remote_name'], 'origin')
        self.assertEqual(cli.select_repository_remote(Path('.'), runner=runner, preferred_remote_hosts=[])['remote_name'], 'origin')
        self.assertEqual(cli.select_repository_remote(Path('.'), runner=runner, preferred_remote_hosts=['gitlab.example.test'])['remote_name'], 'origin')

    def test_config_defaults_and_rejects_urls_arguments_and_wildcards(self):
        config = json.loads((ROOT / 'assets/config.example.json').read_text())
        config.pop('preferred_remote_hosts', None)
        self.assertEqual(cli.validate_config(config)['preferred_remote_hosts'], [])
        config['preferred_remote_hosts'] = ['CODE.EXAMPLE.TEST']
        self.assertEqual(cli.validate_config(config)['preferred_remote_hosts'], ['code.example.test'])
        for invalid in ['example.test', ['https://example.test'], ['*.example.test'], ['example.test:443'], ['example.test\n'], ['-host'], ['a..test'], ['']]:
            config['preferred_remote_hosts'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(cli.ConfigError):
                cli.validate_config(config)

    def test_invalid_preferences_do_not_invoke_git(self):
        runner = Mock()
        with self.assertRaises(cli.ConfigError):
            cli.select_repository_remote(Path('.'), runner=runner, preferred_remote_hosts=['https://example.test'])
        runner.assert_not_called()

    def test_cli_passes_user_config_to_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'raw').mkdir()
            (root / 'wiki').mkdir()
            config = json.loads((ROOT / 'assets/config.example.json').read_text())
            config['knowledge_root'] = str(root)
            config['preferred_remote_hosts'] = ['code.example.test']
            path = root / 'config.json'
            path.write_text(json.dumps(config))
            with patch.object(cli, 'normalize_paths', return_value={'status': 'clean'}) as normalize, contextlib.redirect_stdout(io.StringIO()):
                result = cli.main(['normalize-paths', '--config', str(path), '--stage', 'wiki'], env={})
            self.assertEqual(result, 0)
            self.assertEqual(normalize.call_args.kwargs['preferred_remote_hosts'], ['code.example.test'])

if __name__ == '__main__':
    unittest.main()
