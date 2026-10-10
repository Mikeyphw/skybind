package namespace

import "testing"

func TestStackedTargetAndAliasCannotProveVisibility(t *testing.T) {
	wanted := Signature{Target: "/storage/skybind/demo", FS: "fuse.rclone", Source: "test", MountID: "12"}
	g := Group{Complete: true, Members: []Member{{User: 0, Class: "app"}}}
	classifyVisibility(&g, []Signature{{Target: wanted.Target, FS: wanted.FS, Source: wanted.Source}, {Target: wanted.Target, FS: "fuse.other", Source: "foreign"}}, wanted)
	if g.Visibility != IdentityMismatch {
		t.Fatal(g)
	}
	g = Group{Complete: true, Members: []Member{{User: 0, Class: "app"}}}
	classifyVisibility(&g, []Signature{{Target: "/storage/emulated/0", FS: wanted.FS, Source: wanted.Source}}, wanted)
	if g.Visibility != VisibleAtAlias || g.MatchedPath == wanted.Target {
		t.Fatal(g)
	}
	g.Complete = false
	classifyVisibility(&g, nil, wanted)
	if g.Visibility != Unavailable {
		t.Fatal(g)
	}
}
