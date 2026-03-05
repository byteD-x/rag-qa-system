package auth

import (
	"testing"
)

// Because the new AuthManager relies on a live Redis connection, we skip these tests
// in CI environments without a Redis instance, or they should be rewritten as integration tests.
func TestAuthManager_RedisBehavior(t *testing.T) {
	t.Skip("Skipping AuthManager tests as they require a live Redis instance or miniredis mock.")
}
