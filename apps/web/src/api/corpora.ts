import request from './request';
import type { Corpus, CreateCorpusRequest } from './types';

export function getCorpora() {
    return request.get<{ items: Corpus[]; count: number }>('/corpora');
}

export function createCorpus(data: CreateCorpusRequest) {
    return request.post<Corpus>('/corpora', data);
}

export function deleteCorpus(corpusId: string) {
    return request.delete(`/corpora/${corpusId}`);
}

export function batchDeleteCorpora(corpusIds: string[]) {
    return request.post<{ deleted_count: number }>('/corpora/batch-delete', { corpus_ids: corpusIds });
}
