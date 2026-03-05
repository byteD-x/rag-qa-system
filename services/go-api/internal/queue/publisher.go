package queue

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type Publisher struct {
	client *redis.Client
	key    string
}

// Client 返回 Redis 客户端（用于健康检查）
func (p *Publisher) Client() *redis.Client {
	return p.client
}

func NewPublisher(redisURL, queueKey string) (*Publisher, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	client := redis.NewClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping failed: %w", err)
	}

	return &Publisher{client: client, key: queueKey}, nil
}

func (p *Publisher) PublishIngestJob(ctx context.Context, jobID string) error {
	return p.client.RPush(ctx, p.key, jobID).Err()
}

func (p *Publisher) Close() error {
	return p.client.Close()
}
