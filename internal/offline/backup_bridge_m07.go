package offline

import "errors"

var errInvalidBackupPin = errors.New("invalid pin mount")

// ValidatePinReference reuses the M5 manifest's canonical name/path rules.
func ValidatePinReference(mount, path string) error {
	if !safeName.MatchString(mount) {
		return errInvalidBackupPin
	}
	return validatePath(path)
}
