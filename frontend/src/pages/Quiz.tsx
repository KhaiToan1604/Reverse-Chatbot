import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import FeedbackPanel from "../components/FeedbackPanel";
import QuestionCard from "../components/QuestionCard";
import { Busy, ErrorNote, Meter } from "../components/ui";
import type { AnswerResp, NextResp } from "../types";

export default function Quiz() {
  const sid = Number(useParams().sid);
  const nav = useNavigate();
  const [cur, setCur] = useState<NextResp | null>(null);
  const [result, setResult] = useState<AnswerResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadNext = useCallback(async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const n = await api.next(sid);
      if (n.done) { nav(`/summary/${sid}`, { replace: true }); return; }
      setCur(n);
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }, [sid, nav]);

  useEffect(() => { void loadNext(); }, [loadNext]);

  const submit = async (answer: string) => {
    if (!cur?.question) return;
    setGrading(true); setError(null);
    try { setResult(await api.answer(sid, cur.question.question_id, answer)); }
    catch (e) { setError((e as Error).message); }
    finally { setGrading(false); }
  };

  if (Number.isNaN(sid)) return <ErrorNote error="Đường dẫn phiên học không hợp lệ." />;

  return (
    <section className="stack">
      {cur && <div className="progressbar"><Meter value={(result ? cur.answered + 1 : cur.answered) / cur.total} label="Tiến độ phiên học" /></div>}

      {loading && <Busy>Đang chuẩn bị câu hỏi… lần đầu có thể mất vài giây.</Busy>}
      <ErrorNote error={error} onRetry={cur ? undefined : loadNext} />
      {error && !cur && <Link to="/" className="link">Quay lại trang học</Link>}

      {!loading && cur?.question && (
        <>
          <QuestionCard q={cur.question} index={cur.answered + 1} total={cur.total} disabled={grading || result !== null} onSubmit={submit} />
          {grading && <Busy>Đang chấm câu trả lời…</Busy>}
          {result && <FeedbackPanel r={result} onNext={() => (result.session_finished ? nav(`/summary/${sid}`) : void loadNext())} />}
        </>
      )}
    </section>
  );
}
