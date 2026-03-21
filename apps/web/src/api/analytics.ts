import request from './request';

export interface DashboardFunnel {
  knowledge_bases_created: number | null;
  documents_uploaded: number | null;
  documents_ready: number | null;
  chat_sessions_with_questions: number;
  questions_asked: number;
  answer_outcomes: {
    grounded: number;
    weak_grounded: number;
    refusal: number;
    other: number;
  };
  feedback: {
    up: number;
    down: number;
    flag: number;
  };
}

export interface DashboardIngestHealth {
  summary: {
    total_documents: number;
    ready_documents: number;
    queryable_documents: number;
    failed_documents: number;
    unfinished_documents: number;
    stalled_documents: number;
    dead_letter_documents: number;
    in_progress_documents: number;
    stalled_threshold_hours: number;
  };
  document_status_distribution: { key: string; count: number }[];
  latest_job_status_distribution: { key: string; count: number }[];
  enhancement_status_distribution: { key: string; count: number }[];
  upload_to_ready_latency_ms: {
    count: number;
    avg_ms: number;
    p50_ms: number;
    p95_ms: number;
    max_ms: number;
    unsupported: boolean;
  } | null;
}

export interface DashboardQaQuality {
  summary: {
    assistant_answers: number;
    grounded_answers: number;
    weak_grounded_answers: number;
    refusal_answers: number;
  };
  answer_mode_distribution: { key: string; count: number }[];
  evidence_status_distribution: { key: string; count: number }[];
  zero_hit: {
    selected_candidates_zero: number;
    selected_candidates_zero_rate: number;
    missing_citations: number;
    missing_citations_rate: number;
  };
  low_quality: {
    count: number;
    rate: number;
    score_threshold: number;
    reason_breakdown: { key: string; count: number }[];
  };
  clarification?: {
    triggered_runs: number;
    completed_runs: number;
    pending_runs: number;
    completion_rate: number;
    free_text_runs: number;
    selection_runs: number;
    kind_distribution: { key: string; count: number }[];
  };
}

export interface DashboardDataQuality {
  unsupported_fields: string[];
  degraded_sections: any[];
}

export interface AnalyticsDashboardResponse {
  view: 'personal' | 'admin';
  days: number;
  hot_terms: { term: string; count: number }[];
  zero_hit: {
    trend: { date: string; count: number }[];
    top_queries: { query: string; count: number }[];
  };
  satisfaction: {
    trend: { date: string; up_count: number; down_count: number; flag_count: number }[];
  };
  usage: {
    currency: string;
    summary: {
      assistant_turns: number;
      prompt_tokens: number;
      completion_tokens: number;
      estimated_cost: number;
    };
    trend: any[];
  };
  funnel?: DashboardFunnel;
  ingest_health?: DashboardIngestHealth | null;
  qa_quality?: DashboardQaQuality;
  data_quality?: DashboardDataQuality;
}

export function getAnalyticsDashboard(params: { view: 'personal' | 'admin'; days?: number }) {
  return request.get<AnalyticsDashboardResponse>('/analytics/dashboard', { params });
}
