package lifecycle

import "testing"

func TestAndroidStorageCEGateIsNarrow(t *testing.T) {
	tests := []struct {
		path, value string
		want        bool
	}{
		{"/storage/emulated/0/MyCloud", "false", true},
		{"/storage/emulated/0/MyCloud", "0", true},
		{"/storage/emulated/0/MyCloud", "true", false},
		{"/storage/emulated/0/MyCloud", "1", false},
		{"/storage/emulated/0/MyCloud", "", false},
		{"/storage/emulated/0/MyCloud", "unknown", false},
		{"/storage/emulated/1/MyCloud", "false", false},
		{"/storage/emulated/00/MyCloud", "false", false},
		{"/storage/emulated/0", "false", false},
		{"/mnt/user/0/MyCloud", "false", false},
		{"/data/adb/skybind/cache", "false", false},
	}
	for _, tt := range tests {
		if got := userStorageLockedForProperty(tt.path, tt.value); got != tt.want {
			t.Errorf("path=%q value=%q got=%v want=%v", tt.path, tt.value, got, tt.want)
		}
	}
}
