import importlib.util
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('publication',Path(__file__).resolve().parents[1]/'scripts/check_public_tree.py')
publication=importlib.util.module_from_spec(spec);spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        parent=Path(__file__).resolve().parents[1]/'.test-temp';parent.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_credentials_and_runtime_database_are_not_publishable(self):
        for name in ('credentials.dpapi','installation.json','jobs.sqlite3'):
            path=self.root/name;path.write_text('fixture',encoding='utf8')
            with self.assertRaises(ValueError):publication.validate_files(self.root,[path])

    def test_detected_key_is_rejected_without_echoing_it(self):
        path=self.root/'README.md';canary='gh'+'p_'+'A'*36;path.write_text(canary,encoding='utf8')
        with self.assertRaises(ValueError) as result:publication.validate_files(self.root,[path])
        self.assertNotIn(canary,str(result.exception))

    def test_runtime_variable_reference_is_safe_to_publish(self):
        path=self.root/'README.md';path.write_text('Token wird über CNG_LUMIA_TOKEN oder verdeckt eingegeben.',encoding='utf8')
        self.assertEqual(publication.validate_files(self.root,[path]),1)


if __name__=='__main__':unittest.main()
