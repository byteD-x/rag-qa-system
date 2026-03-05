package config

import (
	"os"
	"strconv"
	"time"
)

type Config struct {
	HTTPAddr         string
	PostgresDSN      string
	RAGServiceURL    string
	QdrantURL        string
	QdrantCollection string
	MaxUploadBytes   int64
	AuthTokenTTL     time.Duration
	AdminUserID      string
	AdminEmail       string
	AdminPassword    string
	MemberUserID     string
	MemberEmail      string
	MemberPassword   string
	AllowedFileTypes map[string]struct{}

	RedisURL       string
	IngestQueueKey string

	S3Endpoint            string
	S3PublicEndpoint      string
	S3AccessKey           string
	S3SecretKey           string
	S3Bucket              string
	S3UseSSL              bool
	S3PresignExpiryMinute int

	// 数据库连接池配置
	DBMaxOpenConns    int
	DBMaxIdleConns    int
	DBConnMaxLifetime time.Duration

	// 大文件处理配置
	MaxInlineTextBytes   int64
	MaxPartialLoadBytes  int64
}

func Load() Config {
	ttlMinutes := getEnvAsInt("AUTH_TOKEN_TTL_MINUTES", 120)
	endpoint := getEnv("S3_ENDPOINT", "minio:9000")

	return Config{
		HTTPAddr:      getEnv("HTTP_ADDR", ":8080"),
		PostgresDSN:   getEnv("POSTGRES_DSN", "postgres://rag:rag@postgres:5432/rag?sslmode=disable"),
		RAGServiceURL: getEnv("RAG_SERVICE_URL", "http://py-rag-service:8000"),
		QdrantURL:     getEnv("QDRANT_URL", "http://qdrant:6333"),
		QdrantCollection: getEnv(
			"QDRANT_COLLECTION",
			"rag_chunks",
		),
		MaxUploadBytes: getEnvAsInt64("MAX_UPLOAD_BYTES", 524288000),
		AuthTokenTTL:   time.Duration(ttlMinutes) * time.Minute,
		AdminUserID:    getEnv("ADMIN_USER_ID", "11111111-1111-1111-1111-111111111111"),
		AdminEmail:     getEnv("ADMIN_EMAIL", "admin@local"),
		AdminPassword:  getEnv("ADMIN_PASSWORD", "ChangeMe123!"),
		MemberUserID:   getEnv("MEMBER_USER_ID", "22222222-2222-2222-2222-222222222222"),
		MemberEmail:    getEnv("MEMBER_EMAIL", "member@local"),
		MemberPassword: getEnv("MEMBER_PASSWORD", "ChangeMe123!"),
		AllowedFileTypes: map[string]struct{}{
			"txt":  {},
			"pdf":  {},
			"docx": {},
		},
		RedisURL:              getEnv("REDIS_URL", "redis://redis:6379/0"),
		IngestQueueKey:        getEnv("INGEST_QUEUE_KEY", "ingest_jobs"),
		S3Endpoint:            endpoint,
		S3PublicEndpoint:      getEnv("S3_PUBLIC_ENDPOINT", endpoint),
		S3AccessKey:           getEnv("S3_ACCESS_KEY", "minioadmin"),
		S3SecretKey:           getEnv("S3_SECRET_KEY", "minioadmin"),
		S3Bucket:              getEnv("S3_BUCKET", "rag-raw"),
		S3UseSSL:              getEnvAsBool("S3_USE_SSL", false),
		S3PresignExpiryMinute: getEnvAsInt("S3_PRESIGN_EXPIRY_MINUTES", 30),
		// 数据库连接池配置
		DBMaxOpenConns:    getEnvAsInt("DB_MAX_OPEN_CONNS", 25),
		DBMaxIdleConns:    getEnvAsInt("DB_MAX_IDLE_CONNS", 5),
		DBConnMaxLifetime: time.Duration(getEnvAsInt("DB_CONN_MAX_LIFETIME_MINUTES", 5)) * time.Minute,
		// 大文件处理配置
		MaxInlineTextBytes:  getEnvAsInt64("MAX_INLINE_TEXT_BYTES", 1<<20),
		MaxPartialLoadBytes: getEnvAsInt64("MAX_PARTIAL_LOAD_BYTES", 10<<20),
	}
}

func getEnv(key, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}

func getEnvAsInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}

	return parsed
}

func getEnvAsInt64(key string, fallback int64) int64 {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil {
		return fallback
	}

	return parsed
}

func getEnvAsBool(key string, fallback bool) bool {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return fallback
	}
	return parsed
}
