package policy

import (
  "skybind/internal/mounts/config"
  "strings"
  "testing"
)
func TestM3ProfilesAndBackwardsCompat(t *testing.T) {
 found:=map[string]bool{}
 for _,p:=range Profiles(){
  if found[p.Name] {t.Fatalf("duplicate %s",p.Name)}
  found[p.Name]=true
  if len(p.Options)!=5 || p.MaxBytes<=0 || p.Description=="" {t.Fatalf("incomplete profile: %+v",p)}
  m:=config.Mount{VFSProfile:p.Name}
  resolved,e:=Resolve(m);if e!=nil || resolved.CacheMode!=p.CacheMode {t.Fatalf("resolve %s: %v",p.Name,e)}
 }
 for _,name:=range []string{"streaming","balanced","documents","minimal","read-only","offline-ready","offline"} {
  if !found[name] {t.Fatalf("missing profile %s",name)}
 }
 ro,_:=Resolve(config.Mount{VFSProfile:"read-only"})
 if !ro.ReadOnly {t.Fatal("read-only profile not enforced")}
 old,_:=Resolve(config.Mount{VFSProfile:"offline"})
 if !strings.Contains(strings.ToLower(old.Description),"not") {t.Fatal("legacy offline mislabeled as pinning")}
}
func TestM3PressureAdvisoryNeverAuthorizesDeletion(t *testing.T) {
 if AssessPressure(-1,10,90,75).State!="unknown" {t.Fatal("missing data accepted")}
 if AssessPressure(90,100,90,75).State!="high" {t.Fatal("pressure ignored")}
 if AssessPressure(50,100,90,75).State!="normal" {t.Fatal("wrong pressure")}
}
