"""Cross-component release/runtime authority checks: candidate ZIP must carry
exact provenance required by on-device runtimeauth.inspect, not only pass ZIP hashes.
"""
from pathlib import Path
import json
import tempfile
import unittest
import zipfile
from test_release_faults import ReleaseFaults, ROOT, rel

class InstalledRuntimeAuthority(unittest.TestCase):
    def test_candidate_contains_exact_verified_runtime_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            source,binary=ReleaseFaults().setup(tmp)
            payload, manifest=rel.collect(source,binary,ROOT/'module',ROOT/'module/webroot')
            with zipfile.ZipFile(source) as z:
                original=z.read('runtime.provenance.json')
            self.assertNotEqual(payload['runtime.provenance.json'],original)
            self.assertEqual(json.loads(payload['runtime.provenance.json'])['engine_path'],rel.NATIVE_ENGINE)
            candidate=d/'candidate.zip'
            rel.write_zip(candidate,payload)
            self.assertEqual(rel.verify_release(candidate)['runtime_provenance_sha256'],rel.sha(payload['runtime.provenance.json']))
            self.assertEqual(rel.verify_release(candidate)['runtime_source_provenance_sha256'],rel.sha(original))
            with zipfile.ZipFile(candidate) as z:
                # Mimic final on-device layout, including root-level provenance.
                root=d/'installed'
                z.extractall(root)
            installed={p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(rel.verify_installed_runtime(installed)['provider'],'newfuture')

    def test_missing_or_replaced_runtime_authority_fails_even_with_rebuilt_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            source,binary=ReleaseFaults().setup(tmp)
            good,_=rel.collect(source,binary,ROOT/'module',ROOT/'module/webroot')
            for corruption in ('missing','tamper','invalid_schema'):
                payload=dict(good)
                if corruption=='missing':
                    del payload['runtime.provenance.json']
                elif corruption=='tamper':
                    payload['system/bin/rclone'] += b'fake-append'
                else:
                    record=json.loads(payload['runtime.provenance.json']);record['arch']='x86_64'
                    payload['runtime.provenance.json']=rel.canonical(record)
                # Re-signing self-hash lists must NOT forge the underlying authority.
                manifest=json.loads(payload['skybind.manifest.json'])
                manifest['files']={name:{'sha256':rel.sha(blob),'size':len(blob)} for name,blob in payload.items() if name not in ('skybind.manifest.json','SHA256SUMS')}
                payload['skybind.manifest.json']=rel.canonical(manifest)
                payload['SHA256SUMS']=''.join(f'{rel.sha(payload[n])}  {n}\n' for n in sorted(payload) if n!='SHA256SUMS').encode()
                archive=d/(corruption+'.zip')
                rel.write_zip(archive,payload)
                with self.subTest(corruption=corruption),self.assertRaises((rel.Reject,KeyError)):
                    rel.verify_release(archive)

if __name__=='__main__':unittest.main()
