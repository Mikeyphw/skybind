package lifecycle
import (
 "skybind/internal/mounts/config"
 "testing"
 "strings"
)
func TestM3ReadOnlyArgsAndNativeFreeSpace(t *testing.T) {
 m:=config.Mount{Name:"cloud",Remote:"cloud:/",Mountpoint:"/mnt/cloud",VFSProfile:"read-only",MinCacheFreeBytes:268435456}
 args,err:=buildArgs(m,"/data/adb/skybind/cache/cloud");if err!=nil{t.Fatal(err)}
 joined:=strings.Join(args," ")
 if !strings.Contains(joined,"--read-only") || !strings.Contains(joined,"--vfs-cache-min-free-space 268435456") {t.Fatalf("security flags missing: %s",joined)}
}
func TestM3LegacyOfflineStillResolves(t *testing.T) {
 m:=config.Mount{Name:"cloud",Remote:"cloud:/",Mountpoint:"/mnt/cloud",VFSProfile:"offline"}
 if _,err:=buildArgs(m,"/data/adb/skybind/cache/cloud");err!=nil{t.Fatal(err)}
}
