export interface Corpus {
    id: string;
    name: string;
    description: string;
    created_at: string;
    updated_at: string;
}

export interface CreateCorpusRequest {
    name: string;
    description: string;
}
