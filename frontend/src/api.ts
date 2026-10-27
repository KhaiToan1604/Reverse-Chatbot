import type * as T from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const ADMIN_KEY = "rc_admin_key";
export const adminKey = {
  get: () => { try { return sessionStorage.getItem(ADMIN_KEY) ?? ""; } catch { return ""; } },
  set: (v: string) => { try { sessionStorage.setItem(ADMIN_KEY, v); } catch { /* bỏ qua */ } },
};

function detailText(d: unknown): string {
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x && typeof x === "object" && "msg" in x ? String((x as { msg: unknown }).msg) : String(x))).join("; ");
  return "Yêu cầu không hợp lệ";
}

async function request<R>(path: string, opts: { method?: string; body?: unknown; form?: FormData; admin?: boolean } = {}): Promise<R> {
  const headers: Record<string, string> = {};
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.admin && adminKey.get()) headers["X-Admin-Key"] = adminKey.get();
  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET"),
      headers,
      body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
    });
  } catch {
    throw new ApiError(0, "Không kết nối được máy chủ. Hãy kiểm tra backend đang chạy.");
  }
  if (!res.ok) {
    let msg = `Lỗi ${res.status}`;
    try { msg = detailText((await res.json()).detail); } catch { /* không phải JSON */ }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as R) : ((await res.json()) as R);
}

export const api = {
  health: () => request<{ status: string; llm: { provider: string; model: string } }>("/health"),
  catalog: () => request<T.CatalogItem[]>("/catalog"),
  createUser: (display_name: string) => request<T.User>("/users", { body: { display_name } }),
  progress: (uid: number) => request<T.ProgressResp>(`/users/${uid}/progress`),
  startSession: (user_id: number, num_questions: number, document_id: number | null) =>
    request<{ session_id: number }>("/quiz/sessions", { body: { user_id, num_questions, document_id } }),
  next: (sid: number) => request<T.NextResp>(`/quiz/sessions/${sid}/next`),
  answer: (sid: number, question_id: number, answer: string) =>
    request<T.AnswerResp>(`/quiz/sessions/${sid}/answer`, { body: { question_id, answer } }),
  summary: (sid: number) => request<T.SummaryResp>(`/quiz/sessions/${sid}/summary`),

  // admin
  docs: () => request<T.DocItem[]>("/documents", { admin: true }),
  uploadDoc: (file: File, title: string) => {
    const f = new FormData();
    f.append("file", file);
    if (title.trim()) f.append("title", title.trim());
    return request<T.DocItem>("/documents", { form: f, admin: true });
  },
  ingestText: (title: string, text: string) => request<T.DocItem>("/documents/text", { body: { title, text }, admin: true }),
  chunks: (id: number) => request<T.ChunkItem[]>(`/documents/${id}/chunks`, { admin: true }),
  deleteDoc: (id: number) => request<void>(`/documents/${id}`, { method: "DELETE", admin: true }),
  generate: (target: { document_id?: number; chunk_id?: number }) =>
    request<T.GenerateResp>("/questions/generate", { body: target, admin: true }),
  questions: (q: { status: string; qtype?: string; level?: string; document_id?: number }) => {
    const p = new URLSearchParams({ status: q.status, limit: "200" });
    if (q.qtype) p.set("qtype", q.qtype);
    if (q.level) p.set("level", q.level);
    if (q.document_id) p.set("document_id", String(q.document_id));
    return request<T.AdminQuestion[]>(`/questions?${p}`, { admin: true });
  },
  report: () => request<T.Report>("/evaluation/report", { admin: true }),
};
