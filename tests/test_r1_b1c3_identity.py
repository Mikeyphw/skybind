import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/dev/android'
sys.path.insert(0, str(SCRIPT))
spec = importlib.util.spec_from_file_location('r1_b1c3_identity', SCRIPT/'r1_b1c3_identity.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PackageUidSurvey(unittest.TestCase):
    def setUp(self):
        self.good = (
            'package:io.github.mikeyphw.skybind uid:10257\n'
            'package:io.github.mikeyphw.skybind.test uid:10258\n'
            'package:com.other.example uid:10259\n'
        )

    def test_valid_complete_mapping(self):
        p = m.package_uid_map(self.good)
        self.assertEqual(m.validate_uid_mapping(p, dict(p)), (10257, 10258))

    def test_shared_app_uid_rejected(self):
        p = m.package_uid_map(self.good+'package:com.bad.shared uid:10257\n')
        with self.assertRaisesRegex(m.Blocked, 'SHARED_OR_AMBIGUOUS_UID'):
            m.validate_uid_mapping(p, dict(p))

    def test_shared_test_uid_rejected(self):
        p = m.package_uid_map(self.good+'package:com.bad.shared uid:10258\n')
        with self.assertRaisesRegex(m.Blocked, 'SHARED_OR_AMBIGUOUS_UID'):
            m.validate_uid_mapping(p, dict(p))

    def test_frontends_disagree(self):
        p = m.package_uid_map(self.good)
        q = dict(p); q[m.b1c.APP] += 1
        with self.assertRaisesRegex(m.Blocked, 'PACKAGE_UID_FRONTENDS_DISAGREE'):
            m.validate_uid_mapping(p, q)

    def test_same_uid_rejected(self):
        p = m.package_uid_map(self.good.replace('uid:10258','uid:10257'))
        with self.assertRaisesRegex(m.Blocked, 'PACKAGE_UID_OWNERSHIP_INVALID'):
            m.validate_uid_mapping(p, dict(p))

    def test_system_uid_rejected(self):
        p = m.package_uid_map(self.good.replace('uid:10257','uid:1000'))
        with self.assertRaisesRegex(m.Blocked, 'PACKAGE_UID_OWNERSHIP_INVALID'):
            m.validate_uid_mapping(p, dict(p))

    def test_missing_test_package_rejected(self):
        p = m.package_uid_map(self.good.replace('package:io.github.mikeyphw.skybind.test uid:10258\n',''))
        with self.assertRaisesRegex(m.Blocked, 'ATTESTED_PACKAGE_MISSING_FROM_UID_ENUMERATION'):
            m.validate_uid_mapping(p, dict(p))

    def test_duplicate_and_garbage_rejected(self):
        for txt in (self.good+self.good, self.good+'WARNING: unknown\n', 'junk', '',
                    self.good+'package:com.foo uid:9999999999999\n'):
            with self.subTest(txt=txt[:20]), self.assertRaises(m.Blocked):
                m.package_uid_map(txt)

    def test_exact_package_names_not_substrings(self):
        p = m.package_uid_map(self.good.replace(m.b1c.APP+' uid:',m.b1c.APP+'.evil uid:'))
        with self.assertRaisesRegex(m.Blocked, 'ATTESTED_PACKAGE_MISSING_FROM_UID_ENUMERATION'):
            m.validate_uid_mapping(p, dict(p))

    def test_no_implicit_device_mutation(self):
        src = (SCRIPT/'r1_b1c3_identity.py').read_text()
        self.assertNotIn('"install"', src)
        self.assertNotIn('"uninstall"', src)
        self.assertNotIn('"reboot"', src)
        self.assertNotIn('"su"', src)
        self.assertIn('"privileged_package_attestor_implemented": False', src)
        self.assertIn('"cross_uid_broker_authorized": False', src)

    def test_failed_queries_do_not_pass(self):
        with patch.object(m.b1c, 'adb_call',return_value=(1,'','permission denied')):
            with self.assertRaises(m.Blocked): m.adb_check('adb','serial','getenforce')

if __name__ == '__main__':
    unittest.main()
