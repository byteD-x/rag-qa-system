package api

import "testing"

func TestValidateAnswerContract(t *testing.T) {
	citations := []Citation{
		{CitationID: "c1", FileName: "a.txt", PageOrLoc: "text:1", ChunkID: "p1", Snippet: "snippet1"},
		{CitationID: "c2", FileName: "b.txt", PageOrLoc: "text:2", ChunkID: "p2", Snippet: "snippet2"},
	}

	tests := []struct {
		name                 string
		answerSentences      []AnswerSentence
		allowCommonKnowledge bool
		wantErr              bool
	}{
		{
			name: "valid source only",
			answerSentences: []AnswerSentence{
				{Text: "来源句 A", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.8},
				{Text: "来源句 B", EvidenceType: "source", CitationIDs: []string{"c2"}, Confidence: 0.7},
			},
			allowCommonKnowledge: false,
			wantErr:              false,
		},
		{
			name: "source without citation",
			answerSentences: []AnswerSentence{
				{Text: "no citation", EvidenceType: "source", CitationIDs: []string{}, Confidence: 0.6},
			},
			allowCommonKnowledge: false,
			wantErr:              true,
		},
		{
			name: "common knowledge with prefix and no citation",
			answerSentences: []AnswerSentence{
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.6},
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c2"}, Confidence: 0.6},
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.6},
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c2"}, Confidence: 0.6},
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.6},
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c2"}, Confidence: 0.6},
				{Text: "【常识补充】可以给出简短背景", EvidenceType: "common_knowledge", CitationIDs: []string{}, Confidence: 0.3},
			},
			allowCommonKnowledge: true,
			wantErr:              false,
		},
		{
			name: "common knowledge missing prefix",
			answerSentences: []AnswerSentence{
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.6},
				{Text: "没有前缀", EvidenceType: "common_knowledge", CitationIDs: []string{}, Confidence: 0.3},
			},
			allowCommonKnowledge: true,
			wantErr:              true,
		},
		{
			name: "common knowledge with citation",
			answerSentences: []AnswerSentence{
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.6},
				{Text: "【常识补充】不能带引用", EvidenceType: "common_knowledge", CitationIDs: []string{"c2"}, Confidence: 0.3},
			},
			allowCommonKnowledge: true,
			wantErr:              true,
		},
		{
			name: "common knowledge not allowed",
			answerSentences: []AnswerSentence{
				{Text: "来源句", EvidenceType: "source", CitationIDs: []string{"c1"}, Confidence: 0.6},
				{Text: "【常识补充】这里是补充信息", EvidenceType: "common_knowledge", CitationIDs: []string{}, Confidence: 0.3},
			},
			allowCommonKnowledge: false,
			wantErr:              true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateAnswerContract(tt.answerSentences, citations, tt.allowCommonKnowledge)
			if tt.wantErr && err == nil {
				t.Fatalf("expected error but got nil")
			}
			if !tt.wantErr && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}
