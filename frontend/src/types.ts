export type QType = "mcq" | "fill_blank" | "short_answer" | "scenario";
export type Level = "recall" | "apply";

export interface User { id: number; display_name: string }
export interface CatalogItem { id: number; title: string; num_topics: number; has_questions: boolean }

export interface PublicQuestion {
  question_id: number; qtype: QType; level: Level; question: string;
  options: string[] | null; topic: string; document: string;
}
export interface NextResp { done: boolean; answered: number; total: number; question: PublicQuestion | null }
export interface AnswerResp {
  score: number; is_correct: boolean; feedback: string; missing_points: string[]; graded_by: "rule" | "llm" | "fallback";
  reference_answer: string; explanation: string; source_quote: string; topic: string;
  mastery: number; next_review_at: string | null; answered: number; total: number; session_finished: boolean;
}
export interface SummaryResp {
  session_id: number; status: string; answered: number; total: number; average_score: number; correct: number;
  weak_topics: { topic: string; avg_score: number }[];
  attempts: { question: string; qtype: QType; level: Level; topic: string; your_answer: string; score: number;
    is_correct: boolean; feedback: string; missing_points: string[] }[];
}
export interface TopicProgress {
  chunk_id: number; document: string; topic: string; mastery: number; streak: number; correct: number; wrong: number;
  seen: boolean; due: boolean; due_at: string | null;
}
export interface ProgressResp {
  user_id: number; overall_mastery: number; topics_total: number; topics_seen: number; topics_due: number; topics: TopicProgress[];
}

// ---- admin ----
export interface DocItem { id: number; title: string; source: string; num_chunks: number; created_at: string; already_existed?: boolean }
export interface ChunkItem { id: number; position: number; heading: string; text: string }
export interface AdminQuestion {
  id: number; chunk_id: number; qtype: QType; level: Level; question: string; options: string[] | null; answer: string;
  explanation: string; rubric: { point: string; weight: number }[] | null; source_quote: string; status: string;
  reject_reason: string; model: string;
}
export interface GenerateResp { created: number; rejected: number; errors: string[]; rejected_reasons: string[]; questions: AdminQuestion[] }
export interface Report {
  generated_total: number; valid: number; rejected: number; auto_pass_rate: number | null;
  valid_by_type_level: Record<string, number>; reject_reasons: Record<string, number>;
}
