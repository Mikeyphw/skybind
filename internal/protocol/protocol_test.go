package protocol

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestBoundsStrictVersion(t *testing.T) {
	ok := `{"schema_version":1,"request_id":"a-1","operation":"runtime.status","class":"query"}`
	if _, e := Decode(strings.NewReader(ok)); e != nil {
		t.Fatal(e)
	}
	for _, in := range []string{`{"schema_version":2,"request_id":"a","operation":"x","class":"query"}`, `{"schema_version":1,"request_id":"a","operation":"exec","class":"run","extra":2}`, ok + ok, strings.Repeat("x", MaxEnvelope+1), `{"schema_version":1,"request_id":"a","operation":"x","class":"file"}`} {
		if _, e := Decode(strings.NewReader(in)); e == nil {
			t.Errorf("accepted: %.50s", in)
		}
	}
	if _, e := MarshalResponse(Success("x", strings.Repeat("x", MaxResponse))); e == nil {
		t.Fatal("large response allowed")
	}
	if _, e := Decode(bytes.NewBuffer([]byte(`{"schema_version":1,"request_id":"a","operation":"x","class":"query","arguments":{}}`))); e != nil {
		t.Fatal(e)
	}
	_ = json.Valid
}
