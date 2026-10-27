import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Busy, ErrorNote, fmtDue, Meter, useLoad } from "../components/ui";
import type { TopicProgress, User } from "../types";

export default function Progress({ user, onMissingUser }: { user: User | null; onMissingUser: () => void }) {
  const nav = useNavigate();
  const [startError, setStartError] = useState<string | null>(null);
  const { data, error, loading, reload } = useLoad(() => (user ? api.progress(user.id) : Promise.resolve(null)), [user?.id]);
  const gone = error !== null && /người dùng/i.test(error);
  useEffect(() => { if (gone) onMissingUser(); }, [gone, onMissingUser]);

  if (!user) return <section className="stack narrow"><p>Nhập tên ở trang <Link to="/">Học</Link> để bắt đầu theo dõi tiến độ.</p></section>;
  if (loading) return <Busy>Đang tải tiến độ…</Busy>;
  if (error || !data) return <ErrorNote error={error ?? "Không tải được tiến độ."} onRetry={reload} />;

  const byDoc = new Map<string, TopicProgress[]>();
  data.topics.forEach((t) => byDoc.set(t.document, [...(byDoc.get(t.document) ?? []), t]));

  const reviewNow = async () => {
    try { nav(`/quiz/${(await api.startSession(user.id, Math.min(10, Math.max(5, data.topics_due)), null)).session_id}`); }
    catch (e) { setStartError((e as Error).message); }
  };

  return (
    <section className="stack narrow">
      <h1 className="display">Tiến độ của {user.display_name}</h1>
      <div className="overall">
        <div>
          <strong className="big">{Math.round(data.overall_mastery * 100)}%</strong>
          <span className="muted"> mức nắm vững chung</span>
        </div>
        <Meter value={data.overall_mastery} label="Mức nắm vững chung" />
        <p className="muted">Đã học {data.topics_seen} / {data.topics_total} mục · {data.topics_due} mục đến hạn ôn</p>
      </div>

      {data.topics_total === 0 && <p>Chưa có tài liệu nào để theo dõi.</p>}
      <ErrorNote error={startError} />
      {data.topics_due > 0 && <div className="actions"><button className="btn" onClick={reviewNow}>Ôn {data.topics_due} mục đến hạn</button></div>}

      {[...byDoc.entries()].map(([doc, topics]) => (
        <div key={doc}>
          <h2>{doc}</h2>
          <ul className="topics">
            {topics.map((t) => (
              <li key={t.chunk_id}>
                <div className="topic-line">
                  <span>{t.topic || `Mục ${t.chunk_id}`}</span>
                  <span className={`chip${t.due ? " chip-due" : ""}`}>{!t.seen ? "Chưa học" : t.due ? "Đến hạn ôn" : fmtDue(t.due_at)}</span>
                </div>
                <Meter value={t.mastery} label={t.topic} />
                <span className="muted">{t.correct} đúng · {t.wrong} sai</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
