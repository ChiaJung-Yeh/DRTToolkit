"""Regression checks for notebook settings refresh and preservation of old runs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desktop_lifecycle_helper',ROOT/'desktop_scripts/desktop_helpers.py')
helper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        (self.root/'desktop_scripts').mkdir();(self.root/'config').mkdir()
        (self.root/'config/study.json').write_text(json.dumps({'paths':{}}),encoding='utf-8')
        self.settings=self.root/'desktop_scripts/desktop_settings.json'
        self.write_settings('first')
        self.root_patch=patch.object(helper,'ROOT',self.root);self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop();helper._refresh_settings();self.temp.cleanup()

    def write_settings(self,run_id):
        self.settings.write_text(json.dumps({'run_id':run_id,'config':'config/study.json','rscript':'Rscript'}),encoding='utf-8')

    def process(self,lines=('stage completed\n',),returncode=0):
        return Mock(stdout=iter(lines),wait=Mock(return_value=returncode))

    def old_manifest(self):
        out=self.root/'outputs/first';out.mkdir(parents=True)
        (out/'manifest.json').write_text(json.dumps({'config_sha256':'old_schema'}),encoding='utf-8')
        (out/'desktop_config.json').write_text('original runtime configuration',encoding='utf-8')
        return out

    def test_imported_function_reads_changed_settings(self):
        imported_run=helper.run
        helper._refresh_settings()
        self.write_settings('second')
        with patch.object(helper.subprocess,'Popen',return_value=self.process()):
            out=imported_run('validate')
        self.assertEqual(out,self.root/'outputs/second')
        self.assertEqual(helper.get_output_dir(),out)

    def test_incompatible_validation_allocates_run_without_overwriting_old_files(self):
        old=self.old_manifest();originals={p.name:p.read_bytes() for p in old.iterdir()}
        with patch.object(helper.subprocess,'Popen',side_effect=[self.process(),self.process()]):
            out=helper.run('validate','evaluate')
        self.assertNotEqual(out,old)
        self.assertEqual(json.loads(self.settings.read_text())['run_id'],out.name)
        for name,data in originals.items():self.assertEqual((old/name).read_bytes(),data)
        self.assertTrue((out/'validate_desktop_console.log').exists())
        self.assertTrue((out/'evaluate_desktop_console.log').exists())

    def test_downstream_conflict_explains_restart_without_allocating_or_running(self):
        old=self.old_manifest()
        with patch.object(helper.subprocess,'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError,'notebook 00'):
                helper.run('predict')
            popen.assert_not_called()
        self.assertEqual(json.loads(self.settings.read_text())['run_id'],'first')
        self.assertEqual((old/'desktop_config.json').read_text(),'original runtime configuration')

    def test_exception_and_log_retain_underlying_error(self):
        line='ValueError: ServiceID values must be unique\n'
        with patch.object(helper.subprocess,'Popen',return_value=self.process([line],1)):
            with self.assertRaisesRegex(RuntimeError,'ServiceID values must be unique'):
                helper.run('validate')
        self.assertEqual((self.root/'outputs/first/validate_desktop_console.log').read_text(),line)

    def test_r_entry_reads_current_run_and_returns_same_output_directory(self):
        helper._refresh_settings();self.write_settings('third')
        with patch.object(helper.subprocess,'Popen',return_value=self.process()) as popen:
            out=helper.run_r('03_Demand_Estimation.R')
        self.assertEqual(out,self.root/'outputs/third')
        self.assertEqual(popen.call_args.args[0][-1],str(self.root/'desktop_scripts/03_Demand_Estimation.R'))

    def test_compatible_windows_config_reuses_same_run_for_python_and_R(self):
        helper._refresh_settings()
        _,content=helper._runtime_config()
        out=self.root/'outputs/first';out.mkdir(parents=True)
        saved=out/'desktop_config.json'
        saved.write_bytes(content.replace('\n','\r\n').encode('utf-8'))
        manifest={'config_sha256':helper._hash(saved),'input_sha256':{},'code_sha256':{}}
        (out/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        with patch.object(helper.subprocess,'Popen',side_effect=[self.process(),self.process()]):
            self.assertEqual(helper.run('validate'),out)
            self.assertEqual(helper.run_r('02_Performance_Drivers.R'),out)
        self.assertEqual(json.loads(self.settings.read_text())['run_id'],'first')


if __name__=='__main__':unittest.main()
