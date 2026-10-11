import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/device'))
import skybind_device as dev

class ProbeContract(unittest.TestCase):
  def proof(self):
    return {'schema_version':1,'nonce':'a'*32,'package':'org.skybind.probe','path':'/storage/emulated/0/Skybind','status':'APP_READ_WRITE_PASS','uid':10256,'write_bytes':32,'read_bytes':32,'read_matches':True}
  def test_matching_app_process_receipt(self):
    dev.validate_probe(self.proof(),'a'*32,'/storage/emulated/0/Skybind',10256)
  def test_no_root_or_adb_shell_substitute(self):
    for uid in (0,2000,9999):
      p=self.proof();p['uid']=uid
      with self.assertRaises(dev.DeviceError):dev.validate_probe(p,'a'*32,p['path'],uid)
  def test_nonce_alias_and_data_mismatch_denied(self):
    for key,bad in [('nonce','b'*32),('path','/storage/emulated/0/alias'),('status','APP_READ_WRITE_FAIL'),('read_bytes',0),('read_matches',False),('package','com.fake.app')]:
      p=self.proof();p[key]=bad
      with self.subTest(key=key),self.assertRaises(dev.DeviceError):dev.validate_probe(p,'a'*32,'/storage/emulated/0/Skybind',10256)
  def test_adb_shell_metacharacters_rejected_before_subprocess(self):
    from pathlib import Path
    for path in ('/storage/emulated/0/a;id','/storage/emulated/0/$(id)',
                 '/storage/emulated/0/a b','/storage/emulated/0/a\nb',
                 '/storage/emulated/0/../secret'):
      with self.subTest(path=path),self.assertRaises(dev.DeviceError):
        dev.capture('/definitely/missing/adb','test-serial',path,Path('/no/file'))
  def test_no_device_fabrication_for_missing_adb(self):
    with self.assertRaises((FileNotFoundError,dev.DeviceError)):
      dev.facts(['/definitely/missing/adb','-s','test'])
if __name__=='__main__':unittest.main()
