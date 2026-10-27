import type { AnswerResp } from "../types";
import { fmtDue, Meter } from "./ui";

export default function FeedbackPanel({ r, onNext }: { r: AnswerResp; onNext: () => void }) {
  const partial = !r.is_correct && r.score > 0;
  const verdict = r.is_correct ? "Đúng" : partial ? "Đúng một phần" : "Chưa đúng";
  const tone = r.is_correct ? "ok" : partial ? "partial" : "bad";
  const pct = Math.round(r.score * 100);

  return (
    <section className={`feedback feedback-${tone}`} aria-live="polite" aria-label="Kết quả câu trả lời">
      <div className="stamp" aria-hidden="true">{verdict}</div>
      <div className="feedback-body">
        <h2 className="sr">{verdict}</h2>
        {(partial || (!r.is_correct && r.graded_by !== "rule")) && <p className="score">Điểm câu này: {pct}%</p>}
        {r.feedback && <p>{r.feedback}</p>}

        {r.missing_points.length > 0 && r.graded_by !== "rule" && (
          <div>
            <p className="sub">Bạn còn thiếu:</p>
            <ul>{r.missing_points.map((p) => <li key={p}>{p}</li>)}</ul>
          </div>
        )}

        {!r.is_correct && <p><span className="sub">Đáp án tham chiếu: </span>{r.reference_answer}</p>}
        {r.explanation && <p className="muted">{r.explanation}</p>}
        {r.source_quote && <blockquote className="source"><span className="sub">Trong tài liệu: </span>“{r.source_quote}”</blockquote>}

        {r.graded_by === "fallback" && (
          <p className="note note-warn">Hệ thống chấm bằng AI đang tạm lỗi nên câu này được chấm bằng từ khoá, kết quả có thể chưa chính xác.</p>
        )}

        <div className="mastery">
          <span className="muted">Mức nắm vững mục “{r.topic || "này"}”</span>
          <Meter value={r.mastery} label="Mức nắm vững" />
          <span className="muted">{Math.round(r.mastery * 100)}%{r.next_review_at ? ` · ${fmtDue(r.next_review_at)}` : ""}</span>
        </div>

        <div className="actions">
          <button className="btn" autoFocus onClick={onNext}>{r.session_finished ? "Xem kết quả" : "Câu tiếp theo"}</button>
        </div>
      </div>
    </section>
  );
}
