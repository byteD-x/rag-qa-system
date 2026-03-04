package api

import "testing"

func TestScopeValidate(t *testing.T) {
	uuid1 := "11111111-1111-1111-1111-111111111111"
	uuid2 := "22222222-2222-2222-2222-222222222222"
	doc1 := "33333333-3333-3333-3333-333333333333"

	tests := []struct {
		name    string
		scope   Scope
		wantErr bool
	}{
		{
			name: "single valid",
			scope: Scope{
				Mode:      "single",
				CorpusIDs: []string{uuid1},
			},
			wantErr: false,
		},
		{
			name: "single invalid corpus count",
			scope: Scope{
				Mode:      "single",
				CorpusIDs: []string{uuid1, uuid2},
			},
			wantErr: true,
		},
		{
			name: "multi valid",
			scope: Scope{
				Mode:      "multi",
				CorpusIDs: []string{uuid1, uuid2},
			},
			wantErr: false,
		},
		{
			name: "multi invalid corpus count",
			scope: Scope{
				Mode:      "multi",
				CorpusIDs: []string{uuid1},
			},
			wantErr: true,
		},
		{
			name: "unsupported mode",
			scope: Scope{
				Mode:      "all",
				CorpusIDs: []string{uuid1},
			},
			wantErr: true,
		},
		{
			name: "invalid corpus uuid",
			scope: Scope{
				Mode:      "single",
				CorpusIDs: []string{"abc"},
			},
			wantErr: true,
		},
		{
			name: "duplicate corpus ids",
			scope: Scope{
				Mode:      "multi",
				CorpusIDs: []string{uuid1, uuid1},
			},
			wantErr: true,
		},
		{
			name: "invalid document uuid",
			scope: Scope{
				Mode:        "single",
				CorpusIDs:   []string{uuid1},
				DocumentIDs: []string{"doc-a"},
			},
			wantErr: true,
		},
		{
			name: "duplicate document ids",
			scope: Scope{
				Mode:        "single",
				CorpusIDs:   []string{uuid1},
				DocumentIDs: []string{doc1, doc1},
			},
			wantErr: true,
		},
		{
			name: "document ids valid",
			scope: Scope{
				Mode:        "single",
				CorpusIDs:   []string{uuid1},
				DocumentIDs: []string{doc1},
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := tt.scope.Validate()
			if tt.wantErr && err == nil {
				t.Fatalf("expected error but got nil")
			}
			if !tt.wantErr && err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}
