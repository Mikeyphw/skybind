from pathlib import Path
import re, unittest
ROOT=Path(__file__).resolve().parents[2]
MODULE=ROOT/'module'
class ModuleLifecycleContracts(unittest.TestCase):
 def test_present_and_static(self):
  for f in ['module.prop','customize.sh','service.sh','post-fs-data.sh','action.sh','uninstall.sh']:
   self.assertTrue((MODULE/f).is_file(),f)
  text=(MODULE/'module.prop').read_text()
  self.assertRegex(text,r'(?m)^id=skybind$')
  self.assertNotIn('rclone-nexus',text.lower())
 def test_no_dynamic_runtime_or_unowned_cleanup(self):
  for name in ['service.sh','post-fs-data.sh','action.sh','uninstall.sh','customize.sh']:
   s="\n".join(line for line in (MODULE/name).read_text().splitlines() if not line.lstrip().startswith("#"))
   self.assertNotRegex(s, r'(?i)(curl\s|wget\s|killall\s|pkill\s|umount\s+-l|rm\s+-rf|nsenter\s|su\s+-c)')
  self.assertIn('uninstall-stop',(MODULE/'uninstall.sh').read_text())
  self.assertNotIn('purge-state',(MODULE/'uninstall.sh').read_text())
  self.assertIn('daemon',(MODULE/'service.sh').read_text())
 def test_platform_worker_isolated(self):
  s=(ROOT/'internal/namespace/worker.go').read_text()
  self.assertIn('runtime.LockOSThread()',s)
  self.assertIn('syscall.RawSyscall(',s)
  self.assertNotIn('exec.Command("sh"',s)
if __name__=='__main__':unittest.main()
