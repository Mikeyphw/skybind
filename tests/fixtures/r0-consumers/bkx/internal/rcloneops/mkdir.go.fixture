package rcloneops

import (
	"context"
	"fmt"
	"strings"
)

// Mkdir creates a directory below an existing rclone location.
func (r Runtime) Mkdir(ctx context.Context, parent, name string) (string, error) {
	clean := strings.TrimSpace(name)
	if clean == "" || clean == "." || clean == ".." || strings.ContainsAny(clean, "/\\\x00") {
		return "", fmt.Errorf("invalid remote folder name")
	}
	child, err := JoinURI(parent, clean)
	if err != nil {
		return "", err
	}
	if err := r.requireConfigForRemote(child); err != nil {
		return "", err
	}
	resolved, err := commandLocation(child)
	if err != nil {
		return "", err
	}
	args := append([]string{"mkdir", resolved}, r.baseArgs()...)
	if _, err := r.commandOutput(ctx, args); err != nil {
		return "", err
	}
	return child, nil
}
