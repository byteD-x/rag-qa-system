package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
	"github.com/google/uuid"

	"rag-p/go-api/internal/auth"
	"rag-p/go-api/internal/config"
	"rag-p/go-api/internal/db"
	"rag-p/go-api/internal/queue"
	"rag-p/go-api/internal/storage"
)

type contextKey string

const claimsKey contextKey = "claims"
const commonKnowledgePrefix = "【常识补充】"
const maxInlineTextBytes int64 = 1 << 20

type API struct {
	cfg        config.Config
	store      *db.Store
	auth       *auth.Manager
	publisher  *queue.Publisher
	s3         *storage.S3Client
	httpClient *http.Client
	logger     *log.Logger
}

func New(cfg config.Config, store *db.Store, authManager *auth.Manager, logger *log.Logger) (*API, error) {
	publisher, err := queue.NewPublisher(cfg.RedisURL, cfg.IngestQueueKey)
	if err != nil {
		return nil, err
	}

	s3Client, err := storage.NewS3Client(
		cfg.S3Endpoint,
		cfg.S3PublicEndpoint,
		cfg.S3AccessKey,
		cfg.S3SecretKey,
		cfg.S3Bucket,
		cfg.S3UseSSL,
		cfg.S3PresignExpiryMinute,
	)
	if err != nil {
		_ = publisher.Close()
		return nil, err
	}

	return &API{
		cfg:       cfg,
		store:     store,
		auth:      authManager,
		publisher: publisher,
		s3:        s3Client,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
		logger: logger,
	}, nil
}

func (a *API) Close() {
	if a.publisher != nil {
		_ = a.publisher.Close()
	}
}

func (a *API) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(30 * time.Second))

	r.Get("/healthz", a.handleHealth)

	r.Route("/v1", func(r chi.Router) {
		r.Post("/auth/login", a.handleLogin)
		r.Group(func(r chi.Router) {
			r.Use(a.requireAuth)

			r.Post("/corpora", a.handleCreateCorpus)
			r.Get("/corpora", a.handleListCorpora)
			r.Post("/corpora/batch-delete", a.handleBatchDeleteCorpora)
			r.Delete("/corpora/{corpusID}", a.handleDeleteCorpus)
			r.Get("/corpora/{corpusID}/documents", a.handleListCorpusDocuments)
			r.Get("/documents/{documentID}", a.handleGetDocumentDetail)
			r.Get("/documents/{documentID}/preview", a.handleGetDocumentPreview)
			r.Put("/documents/{documentID}/content", a.handleUpdateDocumentContent)

			r.Post("/documents/upload-url", a.handleCreateUploadURL)
			r.Post("/documents/upload", a.handleUploadDocument)
			r.Get("/ingest-jobs/{jobID}", a.handleGetIngestJob)

			r.Post("/chat/sessions", a.handleCreateSession)
			r.Get("/chat/sessions", a.handleListSessions)
			r.Post("/chat/sessions/{sessionID}/messages", a.handleCreateMessage)
		})
	})

	return r
}

func (a *API) requireAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		authHeader := r.Header.Get("Authorization")
		if authHeader == "" {
			writeError(w, http.StatusUnauthorized, "missing authorization header")
			return
		}
		parts := strings.SplitN(authHeader, " ", 2)
		if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
			writeError(w, http.StatusUnauthorized, "invalid authorization format")
			return
		}

		claims, ok := a.auth.Validate(parts[1])
		if !ok {
			writeError(w, http.StatusUnauthorized, "invalid or expired token")
			return
		}

		ctx := context.WithValue(r.Context(), claimsKey, claims)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func mustClaims(ctx context.Context) auth.Claims {
	claims, _ := ctx.Value(claimsKey).(auth.Claims)
	return claims
}

func (a *API) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"service": "go-api",
		"time":    time.Now().UTC().Format(time.RFC3339),
	})
}

func (a *API) handleLogin(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if strings.TrimSpace(req.Email) == "" || req.Password == "" {
		writeError(w, http.StatusBadRequest, "email and password are required")
		return
	}

	token, claims, err := a.auth.Login(req.Email, req.Password)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "invalid email or password")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": token,
		"user":         claims,
		"token_type":   "Bearer",
		"expires_in":   int(a.cfg.AuthTokenTTL.Seconds()),
	})
}

func (a *API) handleCreateCorpus(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())
	if claims.Role != auth.RoleAdmin {
		writeError(w, http.StatusForbidden, "only admin can create corpus")
		return
	}

	var req struct {
		Name        string `json:"name"`
		Description string `json:"description"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	if len(req.Name) > 128 {
		writeError(w, http.StatusBadRequest, "name too long, max 128")
		return
	}

	corpus, err := a.store.CreateCorpus(r.Context(), db.CreateCorpusInput{
		Name:        req.Name,
		Description: strings.TrimSpace(req.Description),
		OwnerUserID: claims.UserID,
	})
	if err != nil {
		a.logger.Printf("create corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "create corpus failed")
		return
	}

	writeJSON(w, http.StatusCreated, corpus)
}

func (a *API) handleListCorpora(w http.ResponseWriter, r *http.Request) {
	corpora, err := a.store.ListCorpora(r.Context())
	if err != nil {
		a.logger.Printf("list corpora failed: %v", err)
		writeError(w, http.StatusInternalServerError, "list corpora failed")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": corpora,
		"count": len(corpora),
	})
}

func (a *API) handleDeleteCorpus(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())
	if claims.Role != auth.RoleAdmin {
		writeError(w, http.StatusForbidden, "only admin can delete corpus")
		return
	}

	corpusID := strings.TrimSpace(chi.URLParam(r, "corpusID"))
	if _, err := uuid.Parse(corpusID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid corpusID")
		return
	}

	exists, err := a.store.CorpusExists(r.Context(), corpusID)
	if err != nil {
		a.logger.Printf("query corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query corpus failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "corpus not found")
		return
	}

	storageKeys, err := a.store.ListStorageKeysByCorpus(r.Context(), corpusID)
	if err != nil {
		a.logger.Printf("list corpus storage keys failed: %v", err)
		writeError(w, http.StatusInternalServerError, "list corpus resources failed")
		return
	}

	if err := a.purgeCorpusVectors(r.Context(), corpusID); err != nil {
		a.logger.Printf("purge corpus qdrant points failed: %v", err)
		writeError(w, http.StatusInternalServerError, "purge vector resources failed")
		return
	}
	if err := a.s3.RemoveObjects(r.Context(), storageKeys); err != nil {
		a.logger.Printf("purge corpus objects failed: %v", err)
		writeError(w, http.StatusInternalServerError, "purge object resources failed")
		return
	}

	deleted, err := a.store.DeleteCorpus(r.Context(), corpusID)
	if err != nil {
		a.logger.Printf("delete corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "delete corpus failed")
		return
	}
	if !deleted {
		writeError(w, http.StatusNotFound, "corpus not found")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

func (a *API) handleBatchDeleteCorpora(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())
	if claims.Role != auth.RoleAdmin {
		writeError(w, http.StatusForbidden, "only admin can delete corpus")
		return
	}

	var req struct {
		CorpusIDs []string `json:"corpus_ids"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	normalized, err := normalizeCorpusIDs(req.CorpusIDs)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if len(normalized) > 100 {
		writeError(w, http.StatusBadRequest, "corpus_ids too many, max 100")
		return
	}

	existing, err := a.store.CountCorporaByIDs(r.Context(), normalized)
	if err != nil {
		a.logger.Printf("count batch delete corpora failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query corpus failed")
		return
	}
	if existing != len(normalized) {
		writeError(w, http.StatusBadRequest, "corpus_ids contains non-existent corpus_id")
		return
	}

	storageKeys, err := a.store.ListStorageKeysByCorpora(r.Context(), normalized)
	if err != nil {
		a.logger.Printf("list corpora storage keys failed: %v", err)
		writeError(w, http.StatusInternalServerError, "list corpus resources failed")
		return
	}
	for _, corpusID := range normalized {
		if err := a.purgeCorpusVectors(r.Context(), corpusID); err != nil {
			a.logger.Printf("purge corpus qdrant points failed: corpus=%s err=%v", corpusID, err)
			writeError(w, http.StatusInternalServerError, "purge vector resources failed")
			return
		}
	}
	if err := a.s3.RemoveObjects(r.Context(), storageKeys); err != nil {
		a.logger.Printf("purge corpora objects failed: %v", err)
		writeError(w, http.StatusInternalServerError, "purge object resources failed")
		return
	}

	deletedCount, err := a.store.DeleteCorpora(r.Context(), normalized)
	if err != nil {
		a.logger.Printf("batch delete corpora failed: %v", err)
		writeError(w, http.StatusInternalServerError, "batch delete corpus failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"deleted_count": deletedCount,
	})
}

func (a *API) handleListCorpusDocuments(w http.ResponseWriter, r *http.Request) {
	corpusID := strings.TrimSpace(chi.URLParam(r, "corpusID"))
	if _, err := uuid.Parse(corpusID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid corpusID")
		return
	}

	exists, err := a.store.CorpusExists(r.Context(), corpusID)
	if err != nil {
		a.logger.Printf("query corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query corpus failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "corpus not found")
		return
	}

	items, err := a.store.ListDocumentsByCorpus(r.Context(), corpusID)
	if err != nil {
		a.logger.Printf("list documents by corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "list documents failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"items": items,
		"count": len(items),
	})
}

func (a *API) handleGetDocumentDetail(w http.ResponseWriter, r *http.Request) {
	documentID := strings.TrimSpace(chi.URLParam(r, "documentID"))
	if _, err := uuid.Parse(documentID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid documentID")
		return
	}

	item, err := a.store.GetDocumentByID(r.Context(), documentID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			writeError(w, http.StatusNotFound, "document not found")
			return
		}
		a.logger.Printf("query document detail failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query document detail failed")
		return
	}

	writeJSON(w, http.StatusOK, item)
}

func (a *API) handleGetDocumentPreview(w http.ResponseWriter, r *http.Request) {
	documentID := strings.TrimSpace(chi.URLParam(r, "documentID"))
	if _, err := uuid.Parse(documentID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid documentID")
		return
	}

	item, err := a.store.GetDocumentByID(r.Context(), documentID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			writeError(w, http.StatusNotFound, "document not found")
			return
		}
		a.logger.Printf("query document detail failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query document detail failed")
		return
	}

	if item.FileType == "txt" {
		text, err := a.s3.ReadObjectText(r.Context(), item.StorageKey, maxInlineTextBytes)
		if err != nil {
			if errors.Is(err, storage.ErrObjectTooLarge) {
				writeError(w, http.StatusRequestEntityTooLarge, fmt.Sprintf("txt content too large for inline view, max %d bytes", maxInlineTextBytes))
				return
			}
			a.logger.Printf("read document text failed: %v", err)
			writeError(w, http.StatusInternalServerError, "read document content failed")
			return
		}

		writeJSON(w, http.StatusOK, map[string]any{
			"document":           item,
			"preview_mode":       "text",
			"editable":           true,
			"text":               text,
			"content_type":       "text/plain; charset=utf-8",
			"max_inline_bytes":   maxInlineTextBytes,
			"expires_in_seconds": 0,
		})
		return
	}

	viewURL, err := a.s3.NewDownloadURL(r.Context(), item.StorageKey)
	if err != nil {
		a.logger.Printf("create document preview url failed: %v", err)
		writeError(w, http.StatusInternalServerError, "create document preview url failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"document":           item,
		"preview_mode":       "url",
		"editable":           false,
		"view_url":           viewURL,
		"content_type":       contentTypeByFileType(item.FileType),
		"expires_in_seconds": a.cfg.S3PresignExpiryMinute * 60,
	})
}

func (a *API) handleUpdateDocumentContent(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Content string `json:"content"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	documentID := strings.TrimSpace(chi.URLParam(r, "documentID"))
	if _, err := uuid.Parse(documentID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid documentID")
		return
	}

	item, err := a.store.GetDocumentByID(r.Context(), documentID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			writeError(w, http.StatusNotFound, "document not found")
			return
		}
		a.logger.Printf("query document detail failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query document detail failed")
		return
	}

	if item.FileType != "txt" {
		writeError(w, http.StatusBadRequest, "only txt document supports online edit")
		return
	}

	content := req.Content
	if strings.TrimSpace(content) == "" {
		writeError(w, http.StatusBadRequest, "content is required")
		return
	}

	contentBytes := int64(len([]byte(content)))
	if contentBytes > maxInlineTextBytes {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("content too large for online edit, max %d bytes", maxInlineTextBytes))
		return
	}

	if hasActiveJob, err := a.store.HasActiveIngestJob(r.Context(), documentID); err != nil {
		a.logger.Printf("query ingest job status failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query ingest job status failed")
		return
	} else if hasActiveJob {
		writeError(w, http.StatusConflict, "document ingest is in progress, try later")
		return
	}

	sizeBytes, err := a.s3.PutObjectText(r.Context(), item.StorageKey, content)
	if err != nil {
		a.logger.Printf("update document object failed: %v", err)
		writeError(w, http.StatusInternalServerError, "update document content failed")
		return
	}

	job, err := a.store.CreateReingestJobForDocument(r.Context(), documentID, sizeBytes)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			writeError(w, http.StatusNotFound, "document not found")
			return
		}
		a.logger.Printf("create reingest job failed: %v", err)
		writeError(w, http.StatusInternalServerError, "create reingest job failed")
		return
	}

	if err := a.publisher.PublishIngestJob(r.Context(), job.ID); err != nil {
		a.logger.Printf("enqueue reingest job failed: %v", err)
		_ = a.store.MarkIngestJobFailed(r.Context(), job.ID, documentID, "enqueue ingest job failed")
		writeError(w, http.StatusServiceUnavailable, "enqueue ingest job failed")
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"document_id": documentID,
		"job_id":      job.ID,
		"status":      "queued",
		"message":     "document content updated and queued for re-indexing",
	})
}

func (a *API) handleCreateUploadURL(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())

	var req struct {
		CorpusID  string `json:"corpus_id"`
		FileName  string `json:"file_name"`
		FileType  string `json:"file_type"`
		SizeBytes int64  `json:"size_bytes"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	req.CorpusID = strings.TrimSpace(req.CorpusID)
	req.FileName = strings.TrimSpace(req.FileName)
	req.FileType = strings.ToLower(strings.TrimSpace(req.FileType))

	if req.CorpusID == "" || req.FileName == "" || req.FileType == "" {
		writeError(w, http.StatusBadRequest, "corpus_id, file_name, file_type are required")
		return
	}
	if _, ok := a.cfg.AllowedFileTypes[req.FileType]; !ok {
		writeError(w, http.StatusBadRequest, "unsupported file_type, only txt/pdf/docx")
		return
	}
	if req.SizeBytes <= 0 || req.SizeBytes > a.cfg.MaxUploadBytes {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("size_bytes must be in (0, %d]", a.cfg.MaxUploadBytes))
		return
	}
	if _, err := uuid.Parse(req.CorpusID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid corpus_id")
		return
	}

	exists, err := a.store.CorpusExists(r.Context(), req.CorpusID)
	if err != nil {
		a.logger.Printf("query corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query corpus failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "corpus not found")
		return
	}

	upload, err := a.s3.NewUploadURL(r.Context(), claims.UserID, req.CorpusID, req.FileName, req.FileType)
	if err != nil {
		a.logger.Printf("create upload url failed: %v", err)
		writeError(w, http.StatusInternalServerError, "create upload url failed")
		return
	}

	writeJSON(w, http.StatusOK, upload)
}

func (a *API) handleUploadDocument(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())

	var req struct {
		CorpusID   string `json:"corpus_id"`
		FileName   string `json:"file_name"`
		FileType   string `json:"file_type"`
		SizeBytes  int64  `json:"size_bytes"`
		StorageKey string `json:"storage_key"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	req.CorpusID = strings.TrimSpace(req.CorpusID)
	req.FileName = strings.TrimSpace(req.FileName)
	req.FileType = strings.TrimSpace(strings.ToLower(req.FileType))
	req.StorageKey = strings.TrimSpace(req.StorageKey)

	if req.CorpusID == "" || req.FileName == "" || req.FileType == "" || req.StorageKey == "" {
		writeError(w, http.StatusBadRequest, "corpus_id, file_name, file_type, storage_key are required")
		return
	}
	if _, ok := a.cfg.AllowedFileTypes[req.FileType]; !ok {
		writeError(w, http.StatusBadRequest, "unsupported file_type, only txt/pdf/docx")
		return
	}
	if req.SizeBytes <= 0 || req.SizeBytes > a.cfg.MaxUploadBytes {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("size_bytes must be in (0, %d]", a.cfg.MaxUploadBytes))
		return
	}

	if _, err := uuid.Parse(req.CorpusID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid corpus_id")
		return
	}
	if _, err := uuid.Parse(claims.UserID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid user id in auth claims")
		return
	}

	exists, err := a.store.CorpusExists(r.Context(), req.CorpusID)
	if err != nil {
		a.logger.Printf("query corpus failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query corpus failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "corpus not found")
		return
	}

	objectExists, err := a.s3.ObjectExists(r.Context(), req.StorageKey)
	if err != nil {
		a.logger.Printf("check object exists failed: %v", err)
		writeError(w, http.StatusInternalServerError, "validate uploaded object failed")
		return
	}
	if !objectExists {
		writeError(w, http.StatusBadRequest, "object not found in S3 bucket, upload file first")
		return
	}

	documentID, job, err := a.store.CreateDocumentAndJob(r.Context(), db.CreateDocumentInput{
		CorpusID:   req.CorpusID,
		FileName:   req.FileName,
		FileType:   req.FileType,
		SizeBytes:  req.SizeBytes,
		StorageKey: req.StorageKey,
		CreatedBy:  claims.UserID,
	})
	if err != nil {
		a.logger.Printf("create document/job failed: %v", err)
		writeError(w, http.StatusInternalServerError, "create ingest job failed")
		return
	}

	if err := a.publisher.PublishIngestJob(r.Context(), job.ID); err != nil {
		a.logger.Printf("enqueue ingest job failed: %v", err)
		_ = a.store.MarkIngestJobFailed(r.Context(), job.ID, documentID, "enqueue ingest job failed")
		writeError(w, http.StatusServiceUnavailable, "enqueue ingest job failed")
		return
	}

	writeJSON(w, http.StatusAccepted, map[string]any{
		"document_id": documentID,
		"job_id":      job.ID,
		"status":      "queued",
		"message":     "document metadata accepted and queued for indexing",
	})
}

func (a *API) handleGetIngestJob(w http.ResponseWriter, r *http.Request) {
	jobID := chi.URLParam(r, "jobID")
	if _, err := uuid.Parse(jobID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid jobID")
		return
	}

	job, err := a.store.GetIngestJob(r.Context(), jobID)
	if err != nil {
		if errors.Is(err, db.ErrNotFound) {
			writeError(w, http.StatusNotFound, "job not found")
			return
		}
		a.logger.Printf("query ingest job failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query ingest job failed")
		return
	}

	writeJSON(w, http.StatusOK, job)
}

func (a *API) handleCreateSession(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())

	var req struct {
		Title string `json:"title"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	req.Title = strings.TrimSpace(req.Title)
	if req.Title == "" {
		req.Title = "Untitled Session"
	}
	if len(req.Title) > 200 {
		writeError(w, http.StatusBadRequest, "title too long, max 200")
		return
	}

	session, err := a.store.CreateChatSession(r.Context(), req.Title, claims.UserID)
	if err != nil {
		a.logger.Printf("create chat session failed: %v", err)
		writeError(w, http.StatusInternalServerError, "create chat session failed")
		return
	}

	writeJSON(w, http.StatusCreated, session)
}

func (a *API) handleListSessions(w http.ResponseWriter, r *http.Request) {
	claims := mustClaims(r.Context())

	sessions, err := a.store.ListChatSessions(r.Context(), claims.UserID)
	if err != nil {
		a.logger.Printf("list chat sessions failed: %v", err)
		writeError(w, http.StatusInternalServerError, "list chat sessions failed")
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"items": sessions,
		"count": len(sessions),
	})
}

func (a *API) handleCreateMessage(w http.ResponseWriter, r *http.Request) {
	sessionID := chi.URLParam(r, "sessionID")
	if _, err := uuid.Parse(sessionID); err != nil {
		writeError(w, http.StatusBadRequest, "invalid sessionID")
		return
	}

	exists, err := a.store.ChatSessionExists(r.Context(), sessionID)
	if err != nil {
		a.logger.Printf("query chat session failed: %v", err)
		writeError(w, http.StatusInternalServerError, "query chat session failed")
		return
	}
	if !exists {
		writeError(w, http.StatusNotFound, "chat session not found")
		return
	}

	var req struct {
		Question string `json:"question"`
		Scope    Scope  `json:"scope"`
	}
	if err := decodeJSONBody(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	req.Question = strings.TrimSpace(req.Question)
	if req.Question == "" {
		writeError(w, http.StatusBadRequest, "question is required")
		return
	}
	if len(req.Question) > 8000 {
		writeError(w, http.StatusBadRequest, "question too long, max 8000")
		return
	}
	if err := req.Scope.Validate(); err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	if statusCode, err := a.validateScopeResources(r.Context(), req.Scope); err != nil {
		writeError(w, statusCode, err.Error())
		return
	}

	answerSentences, citations, queryErr := a.queryRAG(r.Context(), req.Question, req.Scope)
	if queryErr == nil {
		if err := validateAnswerContract(answerSentences, citations, req.Scope.AllowCommonKnowledge); err != nil {
			queryErr = fmt.Errorf("invalid rag response contract: %w", err)
		}
	}

	if queryErr != nil {
		a.logger.Printf("rag query failed, fallback to placeholder: %v", queryErr)
		answerSentences = []AnswerSentence{
			{
				Text:         commonKnowledgePrefix + " 当前问答服务暂不可用，请稍后重试。",
				EvidenceType: "common_knowledge",
				CitationIDs:  []string{},
				Confidence:   0.15,
			},
		}
		citations = []Citation{}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"session_id":             sessionID,
		"answer_sentences":       answerSentences,
		"citations":              citations,
		"allow_common_knowledge": req.Scope.AllowCommonKnowledge,
	})
}

func (a *API) validateScopeResources(ctx context.Context, scope Scope) (int, error) {
	existingCorpora, err := a.store.CountCorporaByIDs(ctx, scope.CorpusIDs)
	if err != nil {
		a.logger.Printf("count scope corpora failed: %v", err)
		return http.StatusInternalServerError, errors.New("query scope corpora failed")
	}
	if existingCorpora != len(scope.CorpusIDs) {
		return http.StatusBadRequest, errors.New("scope contains non-existent corpus_id")
	}

	if len(scope.DocumentIDs) > 0 {
		readyDocs, err := a.store.CountReadyDocumentsByIDsAndCorpora(ctx, scope.CorpusIDs, scope.DocumentIDs)
		if err != nil {
			a.logger.Printf("count scope documents failed: %v", err)
			return http.StatusInternalServerError, errors.New("query scope documents failed")
		}
		if readyDocs != len(scope.DocumentIDs) {
			return http.StatusBadRequest, errors.New("scope contains unknown, non-ready, or out-of-corpus document_id")
		}
		return http.StatusOK, nil
	}

	return http.StatusOK, nil
}

func validateAnswerContract(answerSentences []AnswerSentence, citations []Citation, allowCommonKnowledge bool) error {
	if len(answerSentences) == 0 {
		return errors.New("answer_sentences must not be empty")
	}

	citationMap := make(map[string]struct{}, len(citations))
	for _, citation := range citations {
		citationID := strings.TrimSpace(citation.CitationID)
		if citationID == "" {
			return errors.New("citation_id must not be empty")
		}
		citationMap[citationID] = struct{}{}
	}

	commonCount := 0
	for _, sentence := range answerSentences {
		if strings.TrimSpace(sentence.Text) == "" {
			return errors.New("answer sentence text must not be empty")
		}
		if sentence.Confidence < 0 || sentence.Confidence > 1 {
			return errors.New("answer sentence confidence must be between 0 and 1")
		}

		switch sentence.EvidenceType {
		case "source":
			if len(sentence.CitationIDs) == 0 {
				return errors.New("source sentence must contain at least one citation_id")
			}
			for _, citationID := range sentence.CitationIDs {
				trimmed := strings.TrimSpace(citationID)
				if trimmed == "" {
					return errors.New("source sentence contains empty citation_id")
				}
				if _, ok := citationMap[trimmed]; !ok {
					return fmt.Errorf("source sentence citation_id not found: %s", trimmed)
				}
			}
		case "common_knowledge":
			commonCount++
			if len(sentence.CitationIDs) > 0 {
				return errors.New("common_knowledge sentence must not contain citation_ids")
			}
			if !strings.HasPrefix(sentence.Text, commonKnowledgePrefix) {
				return fmt.Errorf("common_knowledge sentence must start with prefix %q", commonKnowledgePrefix)
			}
		default:
			return fmt.Errorf("unsupported evidence_type: %s", sentence.EvidenceType)
		}
	}

	if commonCount > 0 {
		if !allowCommonKnowledge {
			return errors.New("common_knowledge sentence is not allowed by scope")
		}
		ratio := float64(commonCount) / float64(len(answerSentences))
		if ratio > 0.15 {
			return errors.New("common_knowledge sentence ratio exceeds 15% limit")
		}
	}

	return nil
}

func (a *API) queryRAG(ctx context.Context, question string, scope Scope) ([]AnswerSentence, []Citation, error) {
	payload := map[string]any{
		"question": question,
		"scope":    scope,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, nil, err
	}

	url := strings.TrimRight(a.cfg.RAGServiceURL, "/") + "/v1/rag/query"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return nil, nil, fmt.Errorf("rag service returned status=%d body=%s", resp.StatusCode, string(raw))
	}

	var ragResp struct {
		AnswerSentences []AnswerSentence `json:"answer_sentences"`
		Citations       []Citation       `json:"citations"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&ragResp); err != nil {
		return nil, nil, err
	}
	return ragResp.AnswerSentences, ragResp.Citations, nil
}

func contentTypeByFileType(fileType string) string {
	switch strings.ToLower(strings.TrimSpace(fileType)) {
	case "pdf":
		return "application/pdf"
	case "docx":
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	case "txt":
		return "text/plain; charset=utf-8"
	default:
		return "application/octet-stream"
	}
}

func decodeJSONBody(r *http.Request, out any) error {
	if r.Body == nil {
		return errors.New("request body is required")
	}
	limited := io.LimitReader(r.Body, 1<<20)
	defer r.Body.Close()

	decoder := json.NewDecoder(limited)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(out); err != nil {
		return err
	}
	return nil
}

func normalizeCorpusIDs(corpusIDs []string) ([]string, error) {
	if len(corpusIDs) == 0 {
		return nil, errors.New("corpus_ids is required")
	}

	seen := make(map[string]struct{}, len(corpusIDs))
	normalized := make([]string, 0, len(corpusIDs))

	for _, raw := range corpusIDs {
		id := strings.TrimSpace(raw)
		if id == "" {
			return nil, errors.New("corpus_ids contains empty value")
		}
		if _, err := uuid.Parse(id); err != nil {
			return nil, fmt.Errorf("corpus_ids contains invalid uuid: %q", id)
		}
		if _, ok := seen[id]; ok {
			return nil, fmt.Errorf("corpus_ids contains duplicate value: %q", id)
		}
		seen[id] = struct{}{}
		normalized = append(normalized, id)
	}

	return normalized, nil
}

func (a *API) purgeCorpusVectors(ctx context.Context, corpusID string) error {
	qdrantURL := strings.TrimSpace(a.cfg.QdrantURL)
	collection := strings.TrimSpace(a.cfg.QdrantCollection)
	if qdrantURL == "" || collection == "" {
		return errors.New("qdrant config is missing")
	}

	payload := map[string]any{
		"filter": map[string]any{
			"must": []any{
				map[string]any{
					"key": "corpus_id",
					"match": map[string]any{
						"value": corpusID,
					},
				},
			},
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	endpoint := strings.TrimRight(qdrantURL, "/") + "/collections/" + url.PathEscape(collection) + "/points/delete?wait=true"
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil
	}
	if resp.StatusCode >= http.StatusBadRequest {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
		return fmt.Errorf("qdrant delete failed: status=%d body=%s", resp.StatusCode, string(raw))
	}

	return nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]any{
		"error": message,
	})
}
