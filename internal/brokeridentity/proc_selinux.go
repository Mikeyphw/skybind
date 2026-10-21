package brokeridentity

// Procfs SELinux label normalization used solely for kernel /proc/PID/attr/current.
// Android kernels may include one trailing NUL terminator, often visible as
// "ignored null byte" in a shell command substitution. TrimSpace does not
// remove it; blindly trimming all NUL bytes would hide injected contents.
import (
	"bytes"
)

func procSELinuxLabel(raw []byte) (string, error) {
	if len(raw) == 0 || len(raw) > 194 {
		return "", ErrUnverified
	}
	// Accept a bare label, one LF, one NUL, or exactly one of each.
	// A second NUL/newline or an embedded control byte always fails closed.
	switch {
	case bytes.HasSuffix(raw, []byte{'\x00', '\n'}):
		raw = raw[:len(raw)-2]
	case bytes.HasSuffix(raw, []byte{'\n', '\x00'}):
		raw = raw[:len(raw)-2]
	case raw[len(raw)-1] == '\x00' || raw[len(raw)-1] == '\n':
		raw = raw[:len(raw)-1]
	}
	if len(raw) < 8 || len(raw) > 192 || !bytes.HasPrefix(raw, []byte("u:r:")) ||
		bytes.IndexAny(raw, "\x00\r\n\t ") >= 0 {
		return "", ErrUnverified
	}
	return string(raw), nil
}
