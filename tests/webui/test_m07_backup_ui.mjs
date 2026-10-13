import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const app=readFileSync(new URL('../../module/webroot/app.js',import.meta.url),'utf8');
const index=readFileSync(new URL('../../module/webroot/index.html',import.meta.url),'utf8');
test('M7 backup import and explicit two-step restoration UI',()=>{
 for(const op of ['backup.save','backup.preview','backup.restore','ui.settings.preview','ui.settings.apply']) assert.ok(app.includes(op));
 for(const id of ['backupExportButton','backupImportFile','backupPreviewButton','backupRestoreButton','backupPrefsButton']) assert.ok(index.includes(id));
 assert.ok(app.includes('acknowledge_disabled:true'));
 assert.ok(app.includes('acknowledge_public:true'));
 assert.ok(app.includes('all mounts disabled on import'));
 assert.ok(!app.includes('backup.restore-overwrite'));
});
