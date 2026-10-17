#!/usr/bin/env python3
"""Non-executable B0 compatibility stub; old Q10 local builds are retired."""
import json
print(json.dumps({'status':'BLOCKED_BY_POLICY','reason':'ANDROID_APK_BUILDS_GITHUB_ACTIONS_ONLY','release_qualified':False,'device_qualified':False},sort_keys=True))
raise SystemExit(2)
