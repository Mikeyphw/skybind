// Package diagnostics implements bounded, sanitized, private structured events.
package diagnostics

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"
)

const maxFile = 512 * 1024
const maxMessage = 1024

var secretPattern = regexp.MustCompile(`(?i)(password|passphrase|authorization|secret|token|cookie|rc_user|rc_pass|client_secret|api[_-]?key)(\s*[:=]\s*|"\s*:\s*")[^\s,;"}]+`)
var bearer = regexp.MustCompile(`(?i)bearer\s+[^\s,;]+`)
var pathSecret = regexp.MustCompile(`(?i)(password|token|secret)=([^&\s]+)`)

func RedactUnbounded(s string) string {
	s = strings.ToValidUTF8(s, "?")
	s = bearer.ReplaceAllString(s, "Bearer [REDACTED]")
	s = secretPattern.ReplaceAllString(s, "${1}${2}[REDACTED]")
	s = pathSecret.ReplaceAllString(s, "${1}=[REDACTED]")
	return s
}
func Redact(s string) string {
	s = RedactUnbounded(s)
	if len(s) > maxMessage {
		s = strings.ToValidUTF8(s[:maxMessage], "?")
	}
	return s
}

type Entry struct {
	Timestamp  string `json:"timestamp"`
	Level      string `json:"level"`
	Source     string `json:"source"`
	Code       string `json:"code"`
	Message    string `json:"message"`
	Suppressed int    `json:"suppressed"`
}
type Filter struct {
	Level  string `json:"level"`
	Source string `json:"source"`
	Search string `json:"search"`
	Limit  int    `json:"limit"`
}
type Store struct {
	mu        sync.Mutex
	directory string
	path      string
}

func Open(directory string) (*Store, error) {
	st, e := os.Lstat(directory)
	if e != nil {
		return nil, e
	}
	if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm() != 0700 {
		return nil, errors.New("unsafe private logs directory")
	}
	p := filepath.Join(directory, "skybind.jsonl")
	if s, e := os.Lstat(p); e == nil {
		if !s.Mode().IsRegular() || s.Mode().Perm() != 0600 {
			return nil, errors.New("unsafe logs file")
		}
	} else if !os.IsNotExist(e) {
		return nil, e
	}
	return &Store{directory: directory, path: p}, nil
}
func validPart(s string) bool {
	if len(s) == 0 || len(s) > 64 {
		return false
	}
	for _, c := range s {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-' || c == '.') {
			return false
		}
	}
	return true
}
func (s *Store) Write(level, source, code, message string) error {
	if level != "DEBUG" && level != "INFO" && level != "WARN" && level != "ERROR" {
		return errors.New("invalid severity")
	}
	if !validPart(source) || !validPart(code) {
		return errors.New("invalid log source/code")
	}
	b, e := json.Marshal(Entry{Timestamp: time.Now().UTC().Format(time.RFC3339Nano), Level: level, Source: source, Code: code, Message: Redact(message)})
	if e != nil {
		return e
	}
	b = append(b, '\n')
	s.mu.Lock()
	defer s.mu.Unlock()
	f, e := os.OpenFile(s.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return e
	}
	defer f.Close()
	info, e := f.Stat()
	if e != nil {
		return e
	}
	if !info.Mode().IsRegular() || info.Mode().Perm() != 0600 {
		return errors.New("unsafe log file permissions")
	}
	if info.Size()+int64(len(b)) > maxFile {
		if e = f.Truncate(0); e != nil {
			return e
		}
		if _, e = f.Seek(0, 0); e != nil {
			return e
		}
	}
	if _, e = f.Write(b); e != nil {
		return e
	}
	return f.Sync()
}
func (s *Store) Query(filter Filter) ([]Entry, error) {
	if filter.Limit < 1 || filter.Limit > 200 {
		return nil, errors.New("log limit must be 1..200")
	}
	if len(filter.Search) > 128 || len(filter.Source) > 64 {
		return nil, errors.New("filter too long")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	f, e := os.Open(s.path)
	if os.IsNotExist(e) {
		return []Entry{}, nil
	}
	if e != nil {
		return nil, e
	}
	defer f.Close()
	info, e := f.Stat()
	if e != nil {
		return nil, e
	}
	if !info.Mode().IsRegular() || info.Mode().Perm() != 0600 || info.Size() > maxFile {
		return nil, errors.New("unsafe log file")
	}
	var a []Entry
	scan := bufio.NewScanner(f)
	scan.Buffer(make([]byte, 4096), 4096)
	for scan.Scan() {
		var entry Entry
		if json.Unmarshal(scan.Bytes(), &entry) != nil {
			continue
		}
		if filter.Level != "" && entry.Level != filter.Level || filter.Source != "" && entry.Source != filter.Source || filter.Search != "" && !strings.Contains(strings.ToLower(entry.Message), strings.ToLower(filter.Search)) {
			continue
		}
		a = append(a, entry)
		if len(a) > filter.Limit {
			a = a[1:]
		}
	}
	if e := scan.Err(); e != nil {
		return nil, fmt.Errorf("logs bounded scan: %w", e)
	}
	if a == nil {
		a = []Entry{}
	}
	return a, nil
}
