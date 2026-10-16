"""Source-bound tests for V10 sanitized Android accessibility collection."""
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts/dev/device'))
import interactive_webui_gate as m

HOST='vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv'
def xml(nodes):
    return '<?xml version="1.0"?><hierarchy rotation="0">'+nodes+'</hierarchy>'
def node(package,text='',desc=''):
    return f'<node package="{package}" text="{text}" content-desc="{desc}" />'

class AndroidUIReadbackTests(unittest.TestCase):
    def test_success_host_owned_nodes(self):
        data=xml(node(HOST,'Skybind')+node(HOST,'V9: Interactive device qualification'))
        got=m.attested_ui_structure(HOST, command=lambda c,**k:data)
        self.assertEqual(got['capture_status'],'STRUCTURE_VERIFIED')
        self.assertTrue(got['valid_hierarchy'] and got['preview_control'])
        self.assertEqual(got['host_node_count'],2)
    def test_xml_without_declaration(self):
        got=m.attested_ui_structure(HOST,command=lambda c,**k:xml(node(HOST,'Skybind')+node(HOST,desc='Preview transfer policy')).replace('<?xml version="1.0"?>',''))
        self.assertTrue(got['preview_control'])
    def test_other_app_does_not_claim_skybind(self):
        data=xml(node('com.other.app','Skybind')+node('com.other.app','Preview transfer policy')+node(HOST,'Other'))
        got=m.attested_ui_structure(HOST,command=lambda c,**k:data)
        self.assertFalse(got['skybind_page'] or got['preview_control'])
    def test_no_host_nodes(self):
        got=m.attested_ui_structure(HOST,command=lambda c,**k:xml(node('com.other.app','Skybind')))
        self.assertEqual(got['capture_status'],'HOST_NODES_MISSING')
    def test_command_failed_is_non_fatal_sanitized(self):
        def fail(*args,**kwargs):raise m.GateError('raw private data')
        got=m.attested_ui_structure(HOST,command=fail)
        self.assertFalse(got['valid_hierarchy'])
        self.assertNotIn('raw private data',str(got))
    def test_no_xml(self):
        got=m.attested_ui_structure(HOST,command=lambda c,**k:'UI hierarchy dumped to: /dev/tty')
        self.assertEqual(got['capture_status'],'XML_MISSING')
    def test_truncated_xml(self):
        got=m.attested_ui_structure(HOST,command=lambda c,**k:'<?xml version="1.0"?><hierarchy><node')
        self.assertFalse(got['valid_hierarchy'])
    def test_parse_error(self):
        got=m.attested_ui_structure(HOST,command=lambda c,**k:'<hierarchy><node invalid></hierarchy>')
        self.assertEqual(got['capture_status'],'XML_PARSE_FAILED')
    def test_command_private_temporary_file_cleanup(self):
        cmd=m.UI_CAPTURE_COMMAND
        self.assertIn('umask 077',cmd)
        self.assertIn('mktemp',cmd)
        self.assertIn('/data/local/tmp/',cmd)
        self.assertIn('trap',cmd)
        self.assertIn('rm -f',cmd)
        self.assertNotIn('/sdcard',cmd)
    def test_never_export_sensitive_xml(self):
        data=xml(node(HOST,'Skybind')+node(HOST,'Preview transfer policy')+node(HOST,'secret_token_1234'))
        got=m.attested_ui_structure(HOST,command=lambda c,**k:data)
        self.assertNotIn('secret_token_1234',str(got))
        self.assertNotIn('<node',str(got))
    def test_zero_nodes_is_not_pass(self):
        got=m.attested_ui_structure(HOST,command=lambda c,**k:'<hierarchy rotation="0"></hierarchy>')
        self.assertFalse(got['preview_control'])
    def test_bounded_capture(self):
        called=[]
        def cb(cmd,**k):
            called.append(k);return '<hierarchy></hierarchy>'
        m.attested_ui_structure(HOST,command=cb)
        self.assertEqual(called,[{'timeout':25,'max_bytes':512*1024}])

if __name__=='__main__':unittest.main()
