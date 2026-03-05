package auth

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"time"

	"github.com/redis/go-redis/v9"
	"rag-p/go-api/internal/config"
)

const (
	RoleAdmin  = "admin"
	RoleMember = "member"
)

var ErrInvalidCredential = errors.New("invalid email or password")

type Claims struct {
	UserID string `json:"user_id"`
	Role   string `json:"role"`
	Email  string `json:"email"`
}

type Manager struct {
	config config.Config
	ttl    time.Duration
	rdb    *redis.Client
}

func NewManager(cfg config.Config, rdb *redis.Client) *Manager {
	return &Manager{
		config: cfg,
		ttl:    cfg.AuthTokenTTL,
		rdb:    rdb,
	}
}

// CreateToken is used after the handler verifies credentials from database
func (m *Manager) CreateToken(ctx context.Context, claims Claims) (string, error) {
	token, err := newToken()
	if err != nil {
		return "", err
	}
	
	val, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	
	err = m.rdb.SetEx(ctx, "session:"+token, val, m.ttl).Err()
	if err != nil {
		return "", err
	}
	
	return token, nil
}

func (m *Manager) Validate(ctx context.Context, token string) (Claims, bool) {
	val, err := m.rdb.Get(ctx, "session:"+token).Result()
	if err != nil {
		return Claims{}, false
	}
	
	var claims Claims
	if err := json.Unmarshal([]byte(val), &claims); err != nil {
		return Claims{}, false
	}
	
	return claims, true
}

func newToken() (string, error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	return hex.EncodeToString(raw), nil
}
