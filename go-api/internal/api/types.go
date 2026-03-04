package api

import (
	"errors"
	"fmt"
	"strings"

	"github.com/google/uuid"
)

type Scope struct {
	Mode                 string   `json:"mode"`
	CorpusIDs            []string `json:"corpus_ids"`
	DocumentIDs          []string `json:"document_ids,omitempty"`
	AllowCommonKnowledge bool     `json:"allow_common_knowledge"`
}

func (s Scope) Validate() error {
	mode := strings.TrimSpace(strings.ToLower(s.Mode))
	switch mode {
	case "single":
		if len(s.CorpusIDs) != 1 {
			return errors.New("scope.mode=single requires exactly one corpus_id")
		}
	case "multi":
		if len(s.CorpusIDs) < 2 {
			return errors.New("scope.mode=multi requires at least two corpus_ids")
		}
	default:
		return fmt.Errorf("unsupported scope.mode: %q", s.Mode)
	}

	corpusSeen := make(map[string]struct{}, len(s.CorpusIDs))
	for _, id := range s.CorpusIDs {
		trimmed := strings.TrimSpace(id)
		if trimmed == "" {
			return errors.New("scope.corpus_ids contains empty value")
		}
		if _, err := uuid.Parse(trimmed); err != nil {
			return fmt.Errorf("scope.corpus_ids contains invalid uuid: %q", trimmed)
		}
		if _, exists := corpusSeen[trimmed]; exists {
			return fmt.Errorf("scope.corpus_ids contains duplicate value: %q", trimmed)
		}
		corpusSeen[trimmed] = struct{}{}
	}

	docSeen := make(map[string]struct{}, len(s.DocumentIDs))
	for _, id := range s.DocumentIDs {
		trimmed := strings.TrimSpace(id)
		if trimmed == "" {
			return errors.New("scope.document_ids contains empty value")
		}
		if _, err := uuid.Parse(trimmed); err != nil {
			return fmt.Errorf("scope.document_ids contains invalid uuid: %q", trimmed)
		}
		if _, exists := docSeen[trimmed]; exists {
			return fmt.Errorf("scope.document_ids contains duplicate value: %q", trimmed)
		}
		docSeen[trimmed] = struct{}{}
	}
	return nil
}

type AnswerSentence struct {
	Text         string   `json:"text"`
	EvidenceType string   `json:"evidence_type"`
	CitationIDs  []string `json:"citation_ids"`
	Confidence   float64  `json:"confidence"`
}

type Citation struct {
	CitationID string `json:"citation_id"`
	FileName   string `json:"file_name"`
	PageOrLoc  string `json:"page_or_loc"`
	ChunkID    string `json:"chunk_id"`
	Snippet    string `json:"snippet"`
}
