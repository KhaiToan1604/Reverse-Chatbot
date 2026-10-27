import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Busy, ErrorNote, useLoad } from "../components/ui";
import type { User } from "../types";

export default function Home({ user, setUser }: { user: User | null; setUser: (u: User | null) => void }) {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [docId, setDocId] = useState<number | null>(null);
  const [count, setCount] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const catalog = useLoad(api.catalog, []);

  const register = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true); setError(null);
    try { setUser(await api.createUser(name.trim())); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  };

  const start = async () => {
    if (!user) return;
    setBusy(true); setError(null);
    try {
      const s = await api.startSession(user.id, count, docId);
      nav(`/quiz/${s.session_id}`);
    } catch (err) {
      const msg = (err as Error).message;
      if (/người dùng/i.test(msg)) { setUser(null); setError("Tài khoản này không còn tồn tại trên máy chủ. Hãy nhập tên để tạo lại."); }
      else setError(msg);
      setBusy(false);
    }
  };

  if (!user) {
    return (
      <section className="stack narrow">
        <h1 className="display">Tự kiểm tra kiến thức thư viện</h1>
        <p className="lead">Hệ thống đọc tài liệu của Thư viện rồi hỏi bạn: từ con số cần nhớ đến tình huống phải xử lý. Câu nào sai sẽ được hỏi lại đúng lúc bạn sắp quên.</p>
        <form className="stack" onSubmit={register}>
          <label className="field">
            <span>Tên của bạn</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoFocus autoComplete="name" />
          </label>
          <div className="actions"><button className="btn" disabled={busy || !name.trim()}>Bắt đầu</button></div>
        </form>
        <ErrorNote error={error} />
      </section>
    );
  }

  const docs = catalog.data ?? [];
  const selected = docs.find((d) => d.id === docId);
  const needsGen = docId === null ? docs.some((d) => !d.has_questions) : selected ? !selected.has_questions : false;

  return (
    <section className="stack narrow">
      <h1 className="display">Chào {user.display_name}, hôm nay học gì?</h1>

      {catalog.loading && <Busy>Đang tải danh mục tài liệu…</Busy>}
      <ErrorNote error={catalog.error} onRetry={catalog.reload} />

      {!catalog.loading && !catalog.error && docs.length === 0 && (
        <div className="note">
          Chưa có tài liệu nào. Người quản trị cần nạp tài liệu trước tại trang <Link to="/admin">Quản trị</Link>.
        </div>
      )}

      {docs.length > 0 && (
        <>
          <fieldset className="options">
            <legend>Phạm vi</legend>
            <label className={`option${docId === null ? " is-picked" : ""}`}>
              <input type="radio" name="doc" checked={docId === null} onChange={() => setDocId(null)} />
              <span>Tất cả tài liệu</span>
            </label>
            {docs.map((d) => (
              <label key={d.id} className={`option${docId === d.id ? " is-picked" : ""}`}>
                <input type="radio" name="doc" checked={docId === d.id} onChange={() => setDocId(d.id)} />
                <span>{d.title}</span>
                <span className="muted">{d.num_topics} mục</span>
              </label>
            ))}
          </fieldset>

          <fieldset className="options row">
            <legend>Số câu</legend>
            {[5, 10, 15].map((n) => (
              <label key={n} className={`option${count === n ? " is-picked" : ""}`}>
                <input type="radio" name="count" checked={count === n} onChange={() => setCount(n)} />
                <span>{n} câu</span>
              </label>
            ))}
          </fieldset>

          {needsGen && <p className="muted">Một số mục chưa có câu hỏi sẵn; câu hỏi sẽ được tạo khi bạn học nên lần đầu có thể chờ vài giây.</p>}
          <div className="actions">
            <button className="btn" onClick={start} disabled={busy}>{busy ? "Đang tạo phiên…" : "Bắt đầu học"}</button>
            <Link to="/progress" className="link">Xem tiến độ</Link>
          </div>
        </>
      )}
      <ErrorNote error={error} />
    </section>
  );
}
