package networkwatch

import "testing"

func TestCoalescingSignalDoesNotBlock(t *testing.T) {
	ch := make(chan struct{}, 1)
	for i := 0; i < 100000; i++ {
		notify(ch)
	}
	if len(ch) != 1 {
		t.Fatalf("unbounded event queue: %d", len(ch))
	}
	<-ch
	if len(ch) != 0 {
		t.Fatal("coalescing failed")
	}
}
