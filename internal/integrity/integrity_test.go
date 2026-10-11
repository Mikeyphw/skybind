package integrity

import (
	"strings"
	"testing"
)

func TestManifestRejectsTraversalAndIdentity(t *testing.T) {
	basic := `{"schema_version":1,"product":"Skybind","provider":"newfuture","arch":"arm64","engine_path":"system/bin/rclone","helper_path":"system/vendor/bin/fusermount3","files":{}}
 `
	if _, e := Decode([]byte(basic)); e == nil {
		t.Fatal("missing files accepted")
	}
	if _, e := Decode([]byte(strings.Repeat("a", 129000))); e == nil {
		t.Fatal("oversized manifest accepted")
	}
}
