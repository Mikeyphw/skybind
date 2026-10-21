package brokeripc

// ReceiveApprovedGrant accepts an operator-scoped, one-time grant delivered to
// this exact process by the local kernel-authenticated handoff socket. It
// cannot specify the scope or request its own approval. Caller keeps in RAM.
import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"time"
)

const GrantHandoffSocket = "\x00skybind-r1-grant-handoff-v1"

type GrantedToken struct {
	Version   int       `json:"version"`
	Token     string    `json:"token"`
	ExpiresAt time.Time `json:"expires_at"`
}

func ReceiveApprovedGrant(ctx context.Context) (GrantedToken, error) {
	return receiveGrantAt(ctx, GrantHandoffSocket)
}
func receiveGrantAt(ctx context.Context, addr string) (GrantedToken, error) {
	var r GrantedToken
	if ctx == nil {
		return r, errors.New("r1_missing_context")
	}
	c, e := (&net.Dialer{Timeout: 3 * time.Second}).DialContext(ctx, "unix", addr)
	if e != nil {
		return r, e
	}
	defer c.Close()
	d := time.Now().Add(5 * time.Second)
	if t, ok := ctx.Deadline(); ok && t.Before(d) {
		d = t
	}
	_ = c.SetDeadline(d)
	b, e := bufio.NewReader(io.LimitReader(c, 1025)).ReadBytes('\n')
	if e != nil || len(b) > 1024 {
		return GrantedToken{}, errors.New("r1_grant_handoff_incomplete")
	}
	dec := json.NewDecoder(&boundedReader{data: b})
	dec.DisallowUnknownFields()
	if dec.Decode(&r) != nil || dec.Decode(new(any)) != io.EOF || r.Version != 1 || len(r.Token) != 64 || !time.Now().Before(r.ExpiresAt) || r.ExpiresAt.After(time.Now().Add(5*time.Minute+time.Second)) {
		return GrantedToken{}, errors.New("r1_grant_handoff_denied")
	}
	for _, ch := range r.Token {
		if !((ch >= 'a' && ch <= 'f') || (ch >= '0' && ch <= '9')) {
			return GrantedToken{}, errors.New("r1_invalid_token")
		}
	}
	return r, nil
}

type boundedReader struct{ data []byte }

func (b *boundedReader) Read(p []byte) (int, error) {
	if len(b.data) == 0 {
		return 0, io.EOF
	}
	n := copy(p, b.data)
	b.data = b.data[n:]
	return n, nil
}
