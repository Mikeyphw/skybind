package config
import "testing"
func TestM3ProfileChangeRequiresRestartAndRollbackPreview(t *testing.T) {
 old:=Empty();old.Mounts=[]Mount{{Name:"cloud",Remote:"x:/",Mountpoint:"/mnt/cloud",VFSProfile:"balanced"}}
 next:=old;next.Mounts=append([]Mount(nil),old.Mounts...);next.Mounts[0].VFSProfile="read-only"
 diff:=Diff(old,next)
 if len(diff)!=1||!diff[0].Restart||diff[0].Cache!="policy_changed" {t.Fatalf("profile change did not restart: %+v",diff)}
 if _,err:=Validate(raw(next));err!=nil{t.Fatal(err)}
 next.Mounts[0].VFSProfile="evil"
 if _,err:=Validate(raw(next));err==nil{t.Fatal("unknown profile accepted")}
}
