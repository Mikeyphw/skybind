package brokeripc

import (
	"context"
	"strings"
	"testing"
)

func TestConsumerClientRejectsInvalidRequestsWithoutDial(t *testing.T) {
	tests := []Request{
		{Version: 2, Token: strings.Repeat("0", 64), Operation: "rclone.version", Remote: "drive"},
		{Version: 1, Token: "missing", Operation: "rclone.version", Remote: "drive"},
		{Version: 1, Token: strings.Repeat("0", 64), Operation: "", Remote: "drive"},
		{Version: 1, Token: strings.Repeat("0", 64), Operation: "rclone.version", Remote: ""},
	}
	for _, r := range tests {
		if _, e := RequestOnce(context.Background(), r); e == nil {
			t.Fatal("invalid client request attempted", r)
		}
	}
}
