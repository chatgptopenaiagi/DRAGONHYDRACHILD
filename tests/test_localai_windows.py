"""Portable contract checks; actual token/inference proof is a local receipt."""
import io
import subprocess
import unittest
from unittest.mock import patch

from dragonhydra.localai.windows_process import _launch_arguments, start_restricted_process


class LocalAIWindowsProcessTests(unittest.TestCase):
    def setUp(self):
        self.command = [r'C:\approved\llama-server.exe','--host','127.0.0.1']
        self.cwd = r'C:\child\runtime'
        self.env = {'SystemRoot':r'C:\Windows','TEMP':self.cwd}

    def test_native_argument_boundaries_are_preserved(self):
        command = self.command + ['model with spaces.gguf','x&whoami','$(secret)','quote"value']
        line,block = _launch_arguments(command,self.cwd,self.env)
        self.assertEqual(line,subprocess.list2cmdline(command))
        self.assertIn('x&whoami',line)
        self.assertTrue(block.endswith('\0\0'))

    def test_relative_executable_and_shells_are_rejected(self):
        for executable in ('llama-server.exe',r'C:\Windows\cmd.exe',r'C:\Windows\pwsh.exe',r'C:\bad.cmd'):
            with self.subTest(executable=executable), self.assertRaises(ValueError):
                _launch_arguments([executable],self.cwd,self.env)

    def test_parent_traversal_cannot_change_working_directory(self):
        for cwd in (r'C:\child\runtime\..\..\LocalAI','relative'):
            with self.subTest(cwd=cwd), self.assertRaises(ValueError):
                _launch_arguments(self.command,cwd,self.env)

    def test_command_must_be_list_and_have_no_nul(self):
        for command in ('arbitrary command',[self.command[0],'bad\0argument'],[1]):
            with self.subTest(command=command), self.assertRaises(ValueError):
                _launch_arguments(command,self.cwd,self.env)

    def test_environment_cannot_inject_entries(self):
        for env in ({},{'KEY=other':'value'},{'KEY':'value\0MORE=secret'}, {'PATH':'one','path':'two'}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                _launch_arguments(self.command,self.cwd,env)

    def test_command_and_environment_sizes_are_bounded(self):
        with self.assertRaises(ValueError):
            _launch_arguments(self.command+['x'*32767],self.cwd,self.env)
        with self.assertRaises(ValueError):
            _launch_arguments(self.command,self.cwd,{'LONG':'x'*131073})

    def test_absent_windows_restriction_fails_closed(self):
        stream=io.BytesIO()
        with patch('dragonhydra.localai.windows_process.os.name','posix'), patch('dragonhydra.localai.windows_process._spawn_windows') as spawn:
            with self.assertRaisesRegex(OSError,'WINDOWS_RESTRICTION_REQUIRED'):
                start_restricted_process(self.command,cwd=self.cwd,env=self.env,stdout=stream,stderr=stream)
            spawn.assert_not_called()

    def test_restriction_failure_has_no_fallback(self):
        stream=io.BytesIO()
        with patch('dragonhydra.localai.windows_process.os.name','nt'), patch('dragonhydra.localai.windows_process._spawn_windows',side_effect=OSError('TOKEN_FAILED')) as spawn, patch('subprocess.Popen') as fallback:
            with self.assertRaisesRegex(OSError,'TOKEN_FAILED'):
                start_restricted_process(self.command,cwd=self.cwd,env=self.env,stdout=stream,stderr=stream)
            spawn.assert_called_once()
            fallback.assert_not_called()

    def test_default_forbids_children_and_propagates_policy(self):
        stream=io.BytesIO()
        with patch('dragonhydra.localai.windows_process.os.name','nt'), patch('dragonhydra.localai.windows_process._spawn_windows',return_value='child') as spawn:
            self.assertEqual(start_restricted_process(self.command,cwd=self.cwd,env=self.env,stdout=stream,stderr=stream),'child')
            self.assertIs(spawn.call_args.args[-1],False)

    def test_policy_type_and_closed_streams_rejected(self):
        stream=io.BytesIO()
        with self.assertRaises(ValueError):
            start_restricted_process(self.command,cwd=self.cwd,env=self.env,stdout=stream,stderr=stream,allow_children='yes')
        stream.close()
        with self.assertRaises(ValueError):
            start_restricted_process(self.command,cwd=self.cwd,env=self.env,stdout=stream,stderr=stream)
