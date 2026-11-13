import unittest
from unittest.mock import patch
import environment_actions as actions

class EnvironmentTests(unittest.TestCase):
    def test_only_core_exact_versions(self):
        self.assertEqual(actions.validated_specs([{'name':'comfyui-workflow-templates','version':'0.11.107'}]), ['comfyui-workflow-templates==0.11.107'])
        for name, version in [('torch','2.0'),('comfy-kitchen','--upgrade'),('comfy-kitchen','https://bad')]:
            with self.assertRaises(ValueError): actions.validated_specs([{'name':name,'version':version}])

    def test_token_single_use_and_command(self):
        actions._tickets['test']={'expires':actions.time.time()+100,'before':'same','specs':['comfy-kitchen==0.2.41']}
        with patch.object(actions,'fingerprint',return_value='same'), patch.object(actions,'resolved_versions',return_value={'comfy-kitchen':'0.2.41'}), patch.object(actions.subprocess,'run') as run:
            run.return_value.returncode=0;run.return_value.stdout='';run.return_value.stderr=''
            self.assertEqual(actions.execute('test')['status'],'success')
            self.assertIn('--no-deps',run.call_args.args[0])
            with self.assertRaises(ValueError): actions.execute('test')

    def test_companion_packages_are_pinned_in_confirmed_plan(self):
        def dry_run(command, **kwargs):
            report = command[command.index('--report') + 1]
            with open(report, 'w', encoding='utf-8') as f:
                actions.json.dump({'install': [{'metadata': {'name': 'comfyui_workflow_templates', 'version': '0.11.107'}}, {'metadata': {'name': 'comfyui-workflow-templates-core', 'version': '0.3.398'}}]}, f)
            from types import SimpleNamespace
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        with patch.object(actions, 'fingerprint', return_value='same'), patch.object(actions, 'resolved_versions', return_value={'comfyui-workflow-templates':'0.11.106'}), patch.object(actions.subprocess, 'run', side_effect=dry_run):
            result = actions.plan([{'name': 'comfyui-workflow-templates', 'version': '0.11.107'}])
        self.assertTrue(result['executable'])
        self.assertEqual(result['changes'][0]['installed'], '0.11.106')
        self.assertFalse(result['changes'][1]['direct'])
        self.assertIn('comfyui-workflow-templates-core==0.3.398', actions._tickets[result['token']]['specs'])

    def test_drift_refuses_without_install(self):
        actions._tickets['drift']={'expires':actions.time.time()+100,'before':'before','specs':['comfy-kitchen==0.2.41']}
        with patch.object(actions,'fingerprint',return_value='after'), patch.object(actions.subprocess,'run') as run:
            with self.assertRaises(ValueError): actions.execute('drift')
            run.assert_not_called()

if __name__ == '__main__': unittest.main()
