import { useState } from "react";
import { adminKey, api } from "../api";
import { Busy, ErrorNote, levelLabel, typeLabel, useLoad } from "../components/ui";
import type { AdminQuestion, ChunkItem, DocItem, GenerateResp } from "../types";

type Tab = "docs" | "questions" | "report";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("docs");
  const [keyDraft, setKeyDraft] = useState("");
  const [authed, setAuthed] = useState(0); // đổi giá trị để tải lại sau khi nhập khoá
  const docs = useLoad(api.docs, [authed]);
  const locked = docs.error !== null && /X-Admin-Key/.test(docs.error);

  if (locked) {
    return (
      <section className="stack narrow">
        <h1 className="display">Quản trị</h1>
        <p>Máy chủ yêu cầu khoá quản trị (biến <code>ADMIN_API_KEY</code> của backend).</p>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); adminKey.set(keyDraft); setAuthed((n) => n + 1); }}>
          <label className="field"><span>Khoá quản trị</span>
            <input type="password" value={keyDraft} onChange={(e) => setKeyDraft(e.target.value)} autoFocus />
          </label>
          <div className="actions"><button className="btn" disabled={!keyDraft}>Mở khoá</button></div>
        </form>
        {adminKey.get() && <ErrorNote error="Khoá không đúng." />}
      </section>
    );
  }

  return (
    <section className="stack">
      <h1 className="display">Quản trị</h1>
      <div className="tabs" role="tablist">
        {([["docs", "Tài liệu"], ["questions", "Ngân hàng câu hỏi"], ["report", "Báo cáo chất lượng"]] as [Tab, string][]).map(([k, l]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "is-on" : ""} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      {docs.loading && <Busy>Đang tải…</Busy>}
      {!locked && <ErrorNote error={docs.error} onRetry={docs.reload} />}
      {tab === "docs" && !docs.error && <Docs docs={docs.data ?? []} reload={docs.reload} />}
      {tab === "questions" && <Questions docs={docs.data ?? []} />}
      {tab === "report" && <ReportTab />}
    </section>
  );
}

function Docs({ docs, reload }: { docs: DocItem[]; reload: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<string | void>) => {
    setBusy(label); setError(null); setMsg(null);
    try { const m = await fn(); if (m) setMsg(m); reload(); } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const ingestMsg = (d: DocItem) => (d.already_existed ? `“${d.title}” đã có từ trước (nội dung trùng), không nạp lại.` : `Đã nạp “${d.title}”: ${d.num_chunks} mục.`);
  const genMsg = (r: GenerateResp) =>
    `Tạo ${r.created} câu hợp lệ, loại ${r.rejected} câu.` + (r.errors.length ? ` Lỗi: ${r.errors[0]}` : "");

  return (
    <div className="stack">
      <form className="panel stack tight" onSubmit={(e) => { e.preventDefault(); if (file) void run("upload", async () => { const d = await api.uploadDoc(file, title); setFile(null); setTitle(""); return ingestMsg(d); }); }}>
        <h2>Nạp tài liệu</h2>
        <div className="row-fields">
          <label className="field"><span>Tệp (.pdf, .docx, .md, .txt)</span>
            <input type="file" accept=".pdf,.docx,.md,.txt" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <label className="field"><span>Tiêu đề (không bắt buộc)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
        </div>
        <div className="actions"><button className="btn" disabled={!file || busy !== null}>Tải lên</button></div>
      </form>

      <details className="panel">
        <summary>Hoặc dán văn bản</summary>
        <form className="stack tight" onSubmit={(e) => { e.preventDefault(); void run("text", async () => { const d = await api.ingestText(pasteTitle, pasteText); setPasteTitle(""); setPasteText(""); return ingestMsg(d); }); }}>
          <label className="field"><span>Tiêu đề</span><input value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)} /></label>
          <label className="field"><span>Nội dung (hỗ trợ tiêu đề Markdown #, ##)</span><textarea rows={8} value={pasteText} onChange={(e) => setPasteText(e.target.value)} /></label>
          <div className="actions"><button className="btn" disabled={!pasteTitle.trim() || pasteText.trim().length < 20 || busy !== null}>Nạp văn bản</button></div>
        </form>
      </details>

      {busy && <Busy>{busy === "upload" || busy === "text" ? "Đang nạp và tạo embedding…" : "Đang sinh câu hỏi bằng LLM… có thể mất vài chục giây."}</Busy>}
      {msg && <div className="note" role="status">{msg}</div>}
      <ErrorNote error={error} />

      {docs.length === 0 ? <p>Chưa có tài liệu. Hãy nạp tài liệu đầu tiên ở phía trên.</p> : (
        <ul className="doclist">
          {docs.map((d) => <DocRow key={d.id} d={d} busy={busy !== null}
            onGenerate={() => run(`gen${d.id}`, async () => genMsg(await api.generate({ document_id: d.id })))}
            onDelete={() => { if (confirm(`Xoá “${d.title}” cùng toàn bộ câu hỏi và tiến độ liên quan?`)) void run(`del${d.id}`, async () => { await api.deleteDoc(d.id); return `Đã xoá “${d.title}”.`; }); }} />)}
        </ul>
      )}
    </div>
  );
}

function DocRow({ d, busy, onGenerate, onDelete }: { d: DocItem; busy: boolean; onGenerate: () => void; onDelete: () => void }) {
  const [chunks, setChunks] = useState<ChunkItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const toggle = async () => {
    if (chunks) { setChunks(null); return; }
    try { setChunks(await api.chunks(d.id)); } catch (e) { setErr((e as Error).message); }
  };
  return (
    <li className="docrow">
      <div className="docrow-main">
        <div><strong>{d.title}</strong><div className="muted">{d.num_chunks} mục · {d.source}</div></div>
        <div className="actions">
          <button className="btn btn-quiet" onClick={toggle}>{chunks ? "Ẩn các mục" : "Xem các mục"}</button>
          <button className="btn" onClick={onGenerate} disabled={busy}>Sinh câu hỏi</button>
          <button className="btn btn-danger" onClick={onDelete} disabled={busy}>Xoá</button>
        </div>
      </div>
      <ErrorNote error={err} />
      {chunks && <ol className="chunks">{chunks.map((c) => <li key={c.id}><strong>{c.heading || "(không có tiêu đề)"}</strong><p>{c.text}</p></li>)}</ol>}
    </li>
  );
}

function Questions({ docs }: { docs: DocItem[] }) {
  const [status, setStatus] = useState("valid");
  const [qtype, setQtype] = useState("");
  const [level, setLevel] = useState("");
  const [docId, setDocId] = useState("");
  const { data, error, loading, reload } = useLoad(
    () => api.questions({ status, qtype: qtype || undefined, level: level || undefined, document_id: docId ? Number(docId) : undefined }),
    [status, qtype, level, docId],
  );
  return (
    <div className="stack">
      <div className="filters">
        <label className="field"><span>Trạng thái</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="valid">Hợp lệ</option><option value="rejected">Bị loại</option></select></label>
        <label className="field"><span>Loại</span>
          <select value={qtype} onChange={(e) => setQtype(e.target.value)}><option value="">Tất cả</option>{Object.entries(typeLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="field"><span>Mức</span>
          <select value={level} onChange={(e) => setLevel(e.target.value)}><option value="">Tất cả</option>{Object.entries(levelLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="field"><span>Tài liệu</span>
          <select value={docId} onChange={(e) => setDocId(e.target.value)}><option value="">Tất cả</option>{docs.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}</select></label>
      </div>
      {loading && <Busy>Đang tải câu hỏi…</Busy>}
      <ErrorNote error={error} onRetry={reload} />
      {data && data.length === 0 && <p>Không có câu hỏi nào khớp bộ lọc.</p>}
      {data && data.length > 0 && <p className="muted">{data.length} câu{data.length === 200 ? " (hiển thị 200 câu đầu)" : ""}</p>}
      <div className="stack tight">{data?.map((q) => <QRow key={q.id} q={q} />)}</div>
    </div>
  );
}

function QRow({ q }: { q: AdminQuestion }) {
  return (
    <details className="attempt">
      <summary><span className="attempt-mark neutral">{typeLabel[q.qtype] ?? q.qtype}</span><span>{q.question}</span></summary>
      <div className="attempt-body">
        <p className="muted">#{q.id} · {levelLabel[q.level] ?? q.level} · mục {q.chunk_id} · {q.model}</p>
        {q.options && <ol type="A">{q.options.map((o) => <li key={o}>{o}</li>)}</ol>}
        <p><span className="sub">Đáp án: </span>{q.answer}</p>
        {q.rubric && <ul>{q.rubric.map((r) => <li key={r.point}>{r.point} <span className="muted">({Math.round(r.weight * 100)}%)</span></li>)}</ul>}
        {q.source_quote && <blockquote className="source">“{q.source_quote}”</blockquote>}
        {q.reject_reason && <p className="note note-warn">Lý do loại: {q.reject_reason}</p>}
      </div>
    </details>
  );
}

function ReportTab() {
  const { data: r, error, loading, reload } = useLoad(api.report, []);
  if (loading) return <Busy>Đang tải báo cáo…</Busy>;
  if (error || !r) return <ErrorNote error={error ?? "Không tải được báo cáo."} onRetry={reload} />;
  const pct = r.auto_pass_rate === null ? "—" : `${Math.round(r.auto_pass_rate * 100)}%`;
  return (
    <div className="stack narrow">
      <p className="lead">{r.generated_total} câu đã sinh: {r.valid} hợp lệ, {r.rejected} bị loại. Tỉ lệ qua kiểm tra tự động: {pct}.</p>
      <p className="muted">Đây là kiểm tra tự động; chất lượng thật cần người duyệt mẫu (xem README backend, mục Đánh giá).</p>
      <div className="twocol">
        <div><h2>Câu hợp lệ theo loại và mức</h2>
          {Object.keys(r.valid_by_type_level).length === 0 ? <p className="muted">Chưa có.</p> :
            <table><tbody>{Object.entries(r.valid_by_type_level).map(([k, v]) => { const [t, l] = k.split("/"); return <tr key={k}><td>{typeLabel[t as keyof typeof typeLabel] ?? t}, {levelLabel[l as keyof typeof levelLabel] ?? l}</td><td className="num">{v}</td></tr>; })}</tbody></table>}
        </div>
        <div><h2>Lý do bị loại</h2>
          {Object.keys(r.reject_reasons).length === 0 ? <p className="muted">Chưa có câu nào bị loại.</p> :
            <table><tbody>{Object.entries(r.reject_reasons).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>)}</tbody></table>}
        </div>
      </div>
    </div>
  );
}
