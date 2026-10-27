import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Busy, ErrorNote, levelLabel, typeLabel, useLoad } from "../components/ui";
import type { User } from "../types";

export default function Summary({ user }: { user: User | null }) {
  const sid = Number(useParams().sid);
  const nav = useNavigate();
  const { data: s, error, loading, reload } = useLoad(() => api.summary(sid), [sid]);

  const again = async () => {
    if (!user || !s) return;
    try { nav(`/quiz/${(await api.startSession(user.id, s.total, null)).session_id}`); } catch { nav("/"); }
  };

  if (loading) return <Busy>Đang tổng hợp kết quả…</Busy>;
  if (error || !s) return <ErrorNote error={error ?? "Không tải được kết quả."} onRetry={reload} />;

  const pct = Math.round(s.average_score * 100);
  return (
    <section className="stack narrow">
      <h1 className="display">Bạn đúng {s.correct} / {s.answered} câu</h1>
      <p className="lead">Điểm trung bình {pct}%.{s.answered < s.total && " Phiên học chưa kết thúc."}</p>

      {s.weak_topics.length > 0 ? (
        <div>
          <h2>Nên ôn lại</h2>
          <ul className="plain">
            {s.weak_topics.map((t) => (
              <li key={t.topic}><strong>{t.topic}</strong> <span className="muted">({Math.round(t.avg_score * 100)}%)</span></li>
            ))}
          </ul>
        </div>
      ) : (
        <p>Không có mục nào dưới ngưỡng đạt trong phiên này.</p>
      )}

      <div>
        <h2>Chi tiết từng câu</h2>
        <div className="stack tight">
          {s.attempts.map((a, i) => (
            <details key={i} className={`attempt ${a.is_correct ? "ok" : "bad"}`}>
              <summary>
                <span className="attempt-mark" aria-label={a.is_correct ? "Đúng" : "Sai"}>{a.is_correct ? "Đúng" : "Sai"}</span>
                <span>{a.question}</span>
              </summary>
              <div className="attempt-body">
                <p className="muted">{typeLabel[a.qtype]} · {levelLabel[a.level]} · {a.topic}</p>
                <p><span className="sub">Bạn trả lời: </span>{a.your_answer || "(để trống)"}</p>
                {a.feedback && <p>{a.feedback}</p>}
                {a.missing_points.length > 0 && <ul>{a.missing_points.map((p) => <li key={p}>{p}</li>)}</ul>}
              </div>
            </details>
          ))}
        </div>
      </div>

      <div className="actions">
        <button className="btn" onClick={again}>Học tiếp</button>
        <Link to="/progress" className="link">Xem tiến độ</Link>
      </div>
    </section>
  );
}
