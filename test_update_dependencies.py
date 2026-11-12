"""Offline contract tests: no ComfyUI, pip or remote git execution."""
import ast
import pathlib
import unittest

TREE = ast.parse(pathlib.Path(__file__).with_name('__init__.py').read_text(encoding='utf-8'))
NAMES = {'_finish_update', '_dependency_summary', '_update_one_from_manifest'}
NS = {}
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name in NAMES], type_ignores=[]), '<helpers>', 'exec'), NS)

class DependenciesTest(unittest.TestCase):
    def setUp(self):
        NS['_run_git'] = lambda *a, **k: (0, 'abcdef123', '')
        NS['_tail'] = lambda value, count: value[-count:]
        NS['_post_install_setup'] = lambda path: (True, 'dependency log')

    def test_success(self):
        result = NS['_finish_update']('plugin')
        self.assertEqual(result['actual_commit'], 'abcdef123')
        self.assertEqual(result['dependencies_status'], 'success')
        self.assertTrue(result['restart_required'])

    def test_failure_preserves_code_success_and_log(self):
        NS['_post_install_setup'] = lambda path: (False, 'pip failed')
        result = NS['_finish_update']('plugin')
        self.assertEqual(result['code_status'], 'success')
        self.assertEqual(result['dependencies_status'], 'failed')
        self.assertEqual(result['dependencies_log'], 'pip failed')

    def test_exception_reported(self):
        def fail(path):
            raise RuntimeError('installer failed')
        NS['_post_install_setup'] = fail
        self.assertEqual(NS['_finish_update']('plugin')['dependencies_status'], 'failed')

    def test_all_update_entrypoints_call_dependency_helper(self):
        for name in ['plugin_update', 'plugin_update_all', 'plugin_checkout', '_update_one_from_manifest']:
            node = next(n for n in TREE.body if getattr(n, 'name', '') == name)
            self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_finish_update' for n in ast.walk(node)), name)

if __name__ == '__main__':
    unittest.main()
