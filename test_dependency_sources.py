import os, tempfile, unittest
import dependency_sources as sources

class SourceTests(unittest.TestCase):
  def test_scans_declared_requirements_without_execution(self):
    with tempfile.TemporaryDirectory() as root:
      plugin=os.path.join(root,'SafeNode');os.makedirs(plugin)
      with open(os.path.join(plugin,'requirements.txt'),'w') as f:f.write('albumentations==2.0.8\n# comment\ndecord>=0.6\n')
      with open(os.path.join(plugin,'install.py'),'w') as f:f.write("import os\nos.system('pip install evil')\n")
      data=sources.scan(root)
    self.assertEqual(data['plugins'][0]['plugin'],'SafeNode')
    self.assertEqual({x['name'] for x in data['plugins'][0]['requirements']},{'albumentations','decord'})
    self.assertNotIn('evil',{x['name'] for x in data['plugins'][0]['requirements']})

  def test_bad_root_rejected(self):
    with self.assertRaises(ValueError):sources.scan('/missing')

if __name__=='__main__':unittest.main()
