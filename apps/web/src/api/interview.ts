import request from './request';

export interface InterviewQuestion {
  id: string;
  sequence_no: number;
  stem: string;
  question_type?: string;
  difficulty?: string;
  tags?: string[];
  source?: Array<{ document_id?: string; chunk_id?: string; quote?: string }>;
  status?: string;
}

export interface InterviewSessionResponse {
  session_id: string;
  status: string;
  question_count: number;
  question: InterviewQuestion;
}

export interface InterviewAnswerResponse {
  session_id: string;
  question_id: string;
  evaluation: {
    status: string;
    scores: Record<string, number>;
    total_score: number;
    feedback: string;
    weak_points: string[];
  };
  next_question: InterviewQuestion | null;
  completed: boolean;
}

async function unwrap<T>(promise: Promise<{ data?: T } | T>): Promise<T> {
  const response = await promise;
  return ((response as { data?: T }).data ?? response) as T;
}

export function startInterview(data: {
  base_id: string;
  job_position_id: string;
  question_count: number;
  difficulty?: string;
  question_type?: string;
  duration_seconds?: number;
  enable_scoring?: boolean;
}) {
  return unwrap<InterviewSessionResponse>(request.post('/interviews/sessions', data));
}

export function answerInterview(sessionId: string, questionId: string, answer: string) {
  return unwrap<InterviewAnswerResponse>(request.post(`/interviews/sessions/${sessionId}/questions/${questionId}/answer`, { answer }));
}

export function getInterviewReport(sessionId: string) {
  return unwrap<{
    session_id: string;
    status: string;
    total_score: number;
    dimension_scores: Record<string, number>;
    items: Array<InterviewQuestion & { total_score: number; feedback: string; weak_points: string[] }>;
  }>(request.get(`/interviews/sessions/${sessionId}/report`));
}
