package brokeridentity

// An explicitly activated, kernel-peer-authenticated Android PackageManager
// bridge. The trusted peer is Skybind's app process; BKX never speaks this
// protocol. No consumer-controlled identity observation enters the grant store.
import (
	"bufio"
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"strings"
	"sync"
	"syscall"
	"time"
)

const PMBridgeSocket = "\x00skybind-r1-pm-authority-v1"
const pmMaxLine = 48 * 1024

// AuthorityPeerPin is separately operator approved; never taken from agent
// data, a self-reported package name, or a mutable consumer policy.
type AuthorityPeerPin struct {
	UID            uint32
	SELinuxContext string
}

type PMBridge struct {
	Pin       AuthorityPeerPin
	Proc      ProcReader
	mu        sync.Mutex
	listener  *net.UnixListener
	conn      *net.UnixConn
	peerPID   int32
	peerTicks uint64
}

type pmMessage struct {
	Version int       `json:"version"`
	Nonce   string    `json:"nonce"`
	UID     uint32    `json:"uid"`
	Package string    `json:"package"`
	Record  *pmRecord `json:"record,omitempty"`
	Error   string    `json:"error,omitempty"`
}

type pmRecord struct {
	UID                uint32   `json:"uid"`
	PackagesForUID     []string `json:"packages_for_uid"`
	InstalledPackage   string   `json:"installed_package"`
	Signers            []string `json:"signers_der_base64"`
	IsInstalledForUser bool     `json:"installed_for_user"`
}

func (b *PMBridge) validConfig() bool {
	p := b.Pin
	return p.UID >= 10000 && p.UID < 1<<31 && len(p.SELinuxContext) >= 8 && len(p.SELinuxContext) <= 192 && strings.HasPrefix(p.SELinuxContext, "u:r:") && !strings.ContainsAny(p.SELinuxContext, "\n\r\t\x00") && b.Proc != nil
}

func (b *PMBridge) Listen() error {
	if b == nil || !b.validConfig() || os.Geteuid() != 0 {
		return errors.New("pm_bridge_not_operator_authorized")
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.listener != nil {
		return errors.New("pm_bridge_already_started")
	}
	l, err := net.ListenUnix("unix", &net.UnixAddr{Name: PMBridgeSocket, Net: "unix"})
	if err != nil {
		return err
	}
	b.listener = l
	return nil
}

func (b *PMBridge) verifyPeer(pid int32, uid uint32) (uint64, error) {
	if !b.validConfig() || pid <= 0 || uid != b.Pin.UID {
		return 0, ErrUnverified
	}
	stat, e := b.Proc.Read(pid, "stat")
	if e != nil {
		return 0, ErrUnverified
	}
	ticks, e := parseStartTicks(stat, pid)
	if e != nil {
		return 0, ErrUnverified
	}
	status, e := b.Proc.Read(pid, "status")
	if e != nil {
		return 0, ErrUnverified
	}
	observed, e := parseStatusUID(status)
	if e != nil || observed != uid {
		return 0, ErrUnverified
	}
	label, e := b.Proc.Read(pid, "attr/current")
	if e != nil || strings.TrimSpace(string(label)) != b.Pin.SELinuxContext {
		return 0, ErrUnverified
	}
	return ticks, nil
}

// Accept authenticates SO_PEERCRED, /proc UID, process incarnation and exact
// SELinux label before selecting a single authority connection. A caller
// connecting to the abstract socket cannot impersonate the pinned app UID.
func (b *PMBridge) Accept(ctx context.Context) error {
	if b == nil {
		return ErrUnverified
	}
	b.mu.Lock()
	l := b.listener
	b.mu.Unlock()
	if l == nil {
		return errors.New("pm_bridge_not_listening")
	}
	deadline := time.Now().Add(15 * time.Second)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	if err := l.SetDeadline(deadline); err != nil {
		return err
	}
	c, err := l.AcceptUnix()
	if err != nil {
		return err
	}
	raw, e := c.SyscallConn()
	if e != nil {
		c.Close()
		return ErrUnverified
	}
	var cred *syscall.Ucred
	var sockErr error
	if e = raw.Control(func(fd uintptr) {
		cred, sockErr = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED)
	}); e != nil || sockErr != nil || cred == nil || cred.Pid <= 0 || cred.Uid != b.Pin.UID || cred.Gid == 0 {
		c.Close()
		return ErrUnverified
	}
	ticks, e := b.verifyPeer(cred.Pid, cred.Uid)
	if e != nil {
		c.Close()
		return ErrUnverified
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.conn != nil {
		c.Close()
		return errors.New("pm_bridge_already_connected")
	}
	b.conn = c
	b.peerPID = cred.Pid
	b.peerTicks = ticks
	return nil
}

func (b *PMBridge) Close() error {
	if b == nil {
		return nil
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.conn != nil {
		_ = b.conn.Close()
		b.conn = nil
	}
	if b.listener != nil {
		e := b.listener.Close()
		b.listener = nil
		return e
	}
	return nil
}

// readMessage rejects oversized, duplicate-key and unknown-field responses.
// JSON schema is deliberately flat apart from the known record object/arrays.
func readPMMessage(raw []byte) (pmMessage, error) {
	var m pmMessage
	if len(raw) == 0 || len(raw) > pmMaxLine || rejectPMDuplicateKeys(raw) != nil {
		return m, ErrUnverified
	}
	d := json.NewDecoder(strings.NewReader(string(raw)))
	d.DisallowUnknownFields()
	if e := d.Decode(&m); e != nil {
		return pmMessage{}, ErrUnverified
	}
	if e := d.Decode(new(any)); e != io.EOF {
		return pmMessage{}, ErrUnverified
	}
	if m.Version != 1 || len(m.Nonce) != 64 || len(m.Error) > 128 {
		return pmMessage{}, ErrUnverified
	}
	if _, e := hex.DecodeString(m.Nonce); e != nil {
		return pmMessage{}, ErrUnverified
	}
	return m, nil
}

// rejectPMDuplicateKeys walks all nested structures, including records.
func rejectPMDuplicateKeys(raw []byte) error {
	d := json.NewDecoder(strings.NewReader(string(raw)))
	var visit func() error
	visit = func() error {
		t, e := d.Token()
		if e != nil {
			return e
		}
		delim, ok := t.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := map[string]bool{}
			for d.More() {
				k, e := d.Token()
				if e != nil {
					return e
				}
				s, ok := k.(string)
				if !ok || seen[s] {
					return ErrUnverified
				}
				seen[s] = true
				if e = visit(); e != nil {
					return e
				}
			}
			end, e := d.Token()
			if e != nil || end != json.Delim('}') {
				return ErrUnverified
			}
		case '[':
			for d.More() {
				if e = visit(); e != nil {
					return e
				}
			}
			end, e := d.Token()
			if e != nil || end != json.Delim(']') {
				return ErrUnverified
			}
		default:
			return ErrUnverified
		}
		return nil
	}
	if e := visit(); e != nil {
		return e
	}
	if _, e := d.Token(); e != io.EOF {
		return ErrUnverified
	}
	return nil
}

func pmRoundTrip(ctx context.Context, conn net.Conn, request pmMessage) (pmMessage, error) {
	if conn == nil {
		return pmMessage{}, ErrUnverified
	}
	deadline := time.Now().Add(3 * time.Second)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	if e := conn.SetDeadline(deadline); e != nil {
		return pmMessage{}, ErrUnverified
	}
	data, _ := json.Marshal(request)
	data = append(data, '\n')
	if _, e := conn.Write(data); e != nil {
		return pmMessage{}, ErrUnverified
	}
	r := bufio.NewReader(io.LimitReader(conn, pmMaxLine+1))
	raw, e := r.ReadBytes('\n')
	if e != nil || len(raw) > pmMaxLine {
		return pmMessage{}, ErrUnverified
	}
	response, e := readPMMessage(raw)
	if e != nil {
		return pmMessage{}, ErrUnverified
	}
	a, _ := hex.DecodeString(response.Nonce)
	b, _ := hex.DecodeString(request.Nonce)
	if subtle.ConstantTimeCompare(a, b) != 1 || response.UID != request.UID || response.Package != request.Package || response.Error != "" || response.Record == nil {
		return pmMessage{}, ErrUnverified
	}
	return response, nil
}

var _ PackageAuthority = (*PMBridge)(nil)

func (b *PMBridge) LookupInstalled(ctx context.Context, uid uint32, pkg string) (PlatformPackageRecord, error) {
	if b == nil || uid < 10000 || len(pkg) < 3 || len(pkg) > 255 || strings.ContainsAny(pkg, "\x00\n\r\t/") {
		return PlatformPackageRecord{}, ErrUnverified
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.conn == nil {
		return PlatformPackageRecord{}, ErrUnverified
	}
	before, e := b.verifyPeer(b.peerPID, b.Pin.UID)
	if e != nil || before != b.peerTicks {
		_ = b.conn.Close()
		b.conn = nil
		return PlatformPackageRecord{}, ErrUnverified
	}
	nonce := make([]byte, 32)
	if _, e = rand.Read(nonce); e != nil {
		return PlatformPackageRecord{}, ErrUnverified
	}
	request := pmMessage{Version: 1, Nonce: hex.EncodeToString(nonce), UID: uid, Package: pkg}
	response, e := pmRoundTrip(ctx, b.conn, request)
	after, ae := b.verifyPeer(b.peerPID, b.Pin.UID)
	if e != nil || ae != nil || before != after {
		_ = b.conn.Close()
		b.conn = nil
		return PlatformPackageRecord{}, ErrUnverified
	}
	r := response.Record
	if r.UID != uid || r.InstalledPackage != pkg || !r.IsInstalledForUser || len(r.PackagesForUID) != 1 || r.PackagesForUID[0] != pkg || len(r.Signers) != 1 {
		return PlatformPackageRecord{}, ErrUnverified
	}
	der, e := base64.StdEncoding.Strict().DecodeString(r.Signers[0])
	if e != nil || len(der) < 64 || len(der) > 8192 {
		return PlatformPackageRecord{}, ErrUnverified
	}
	return PlatformPackageRecord{UID: r.UID, PackagesForUID: r.PackagesForUID, InstalledPackage: r.InstalledPackage, APKContentsSigners: [][]byte{der}, IsInstalledForUser: true}, nil
}

// Diagnostic state deliberately excludes signing certificates and tokens.
func (b *PMBridge) State() string {
	if b == nil {
		return "DISABLED"
	}
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.conn != nil {
		return "CONNECTED_UNQUALIFIED"
	}
	if b.listener != nil {
		return "LISTENING_FOR_PINNED_AUTHORITY"
	}
	return "DISABLED"
}

// Compile guard: the local socket location is never derived from a caller.
