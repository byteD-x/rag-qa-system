package api

import "testing"

func TestNormalizeCorpusIDs(t *testing.T) {
	validA := "11111111-1111-1111-1111-111111111111"
	validB := "22222222-2222-2222-2222-222222222222"

	tests := []struct {
		name    string
		input   []string
		wantErr bool
	}{
		{
			name:    "valid ids",
			input:   []string{validA, validB},
			wantErr: false,
		},
		{
			name:    "empty list",
			input:   []string{},
			wantErr: true,
		},
		{
			name:    "contains empty value",
			input:   []string{validA, "   "},
			wantErr: true,
		},
		{
			name:    "contains invalid uuid",
			input:   []string{validA, "abc"},
			wantErr: true,
		},
		{
			name:    "contains duplicate value",
			input:   []string{validA, validA},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			normalized, err := normalizeCorpusIDs(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("expected error but got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if len(normalized) != len(tt.input) {
				t.Fatalf("unexpected normalized size: got=%d want=%d", len(normalized), len(tt.input))
			}
		})
	}
}
