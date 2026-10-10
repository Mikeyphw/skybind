package previewproof

import (
	"sync"
	"testing"
	"time"
)

func TestOneUseRaceExpiry(t *testing.T) {
	s := New()
	b := Binding{Action: "apply", Subject: "registry", Revision: 1, Digest: "123"}
	tok, _ := s.Issue(b, time.Minute)
	var wg sync.WaitGroup
	wins := make(chan bool, 100)
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); wins <- s.Consume(tok, b) == nil }()
	}
	wg.Wait()
	close(wins)
	num := 0
	for win := range wins {
		if win {
			num++
		}
	}
	if num != 1 {
		t.Fatalf("spent %d times", num)
	}
	tok, _ = s.Issue(b, time.Minute)
	bad := b
	bad.Revision = 2
	if s.Consume(tok, bad) == nil {
		t.Fatal("revision swap")
	}
	if s.Consume(tok, b) == nil {
		t.Fatal("mismatched proof reused")
	}
	s.now = func() time.Time { return time.Now().Add(time.Hour) }
	tok, _ = s.Issue(b, time.Second)
	s.now = func() time.Time { return time.Now().Add(2 * time.Hour) }
	if s.Consume(tok, b) == nil {
		t.Fatal("expired proof")
	}
}
