import unittest
from restart_assessment import classify_file, assess_restart

class RestartAssessmentTests(unittest.TestCase):
    def test_backend_requires_restart(self):
        result = assess_restart(['py/nodes/foo.py', 'web/foo.js'])
        self.assertEqual(result['level'], 'required')
        self.assertIn('py/nodes/foo.py', result['reason'])

    def test_frontend_and_docs_are_optional(self):
        result = assess_restart(['web/foo.js', 'docs/README.md', 'static/style.css'])
        self.assertEqual(result['level'], 'optional')

    def test_unknown_is_conservative(self):
        self.assertEqual(assess_restart(['model.bin'])['level'], 'required')
        self.assertEqual(assess_restart(None)['level'], 'required')
        self.assertEqual(assess_restart([], first_install=True)['level'], 'required')
        self.assertEqual(assess_restart([], dependencies_changed=True)['level'], 'required')

    def test_test_python_does_not_require_restart(self):
        self.assertEqual(classify_file('tests/test_api.py'), 'doc')
        self.assertEqual(classify_file('py/runtime.py'), 'backend')

if __name__ == '__main__':
    unittest.main()
