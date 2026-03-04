package auth

import (
	"errors"
	"testing"
	"time"

	"rag-p/go-api/internal/config"
)

func testConfig() config.Config {
	return config.Config{
		AuthTokenTTL:   time.Minute,
		AdminUserID:    "11111111-1111-1111-1111-111111111111",
		AdminEmail:     "admin@local",
		AdminPassword:  "ChangeMe123!",
		MemberUserID:   "22222222-2222-2222-2222-222222222222",
		MemberEmail:    "member@local",
		MemberPassword: "ChangeMe123!",
	}
}

func TestManagerLoginAndValidateAdmin(t *testing.T) {
	m := NewManager(testConfig())

	token, claims, err := m.Login("ADMIN@local", "ChangeMe123!")
	if err != nil {
		t.Fatalf("login failed: %v", err)
	}
	if len(token) == 0 {
		t.Fatalf("token should not be empty")
	}
	if claims.Role != RoleAdmin {
		t.Fatalf("unexpected role: got=%s want=%s", claims.Role, RoleAdmin)
	}

	validated, ok := m.Validate(token)
	if !ok {
		t.Fatalf("token should be valid")
	}
	if validated.UserID != claims.UserID || validated.Email != claims.Email || validated.Role != claims.Role {
		t.Fatalf("validated claims mismatch")
	}
}

func TestManagerLoginInvalidCredential(t *testing.T) {
	m := NewManager(testConfig())

	_, _, err := m.Login("admin@local", "wrong-password")
	if !errors.Is(err, ErrInvalidCredential) {
		t.Fatalf("expected ErrInvalidCredential, got %v", err)
	}
}

func TestManagerValidateExpiredToken(t *testing.T) {
	m := NewManager(testConfig())

	token, _, err := m.Login("member@local", "ChangeMe123!")
	if err != nil {
		t.Fatalf("login failed: %v", err)
	}

	m.mu.Lock()
	sess := m.tokens[token]
	sess.expiresAt = time.Now().Add(-time.Second)
	m.tokens[token] = sess
	m.mu.Unlock()

	if _, ok := m.Validate(token); ok {
		t.Fatalf("expired token should be invalid")
	}

	m.mu.RLock()
	_, exists := m.tokens[token]
	m.mu.RUnlock()
	if exists {
		t.Fatalf("expired token should be removed from cache")
	}
}
