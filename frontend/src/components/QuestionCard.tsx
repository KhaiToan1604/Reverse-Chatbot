import { useEffect, useRef, useState } from "react";
import type { PublicQuestion } from "../types";
import { levelLabel, typeLabel } from "./ui";

interface Props {
  q: PublicQuestion;
  index: number;
  total: number;
  disabled: boolean;
  onSubmit: (answer: string) => void;
}

/** Câu hỏi dạng thẻ mục lục thư viện: dòng đỏ ở đầu, dòng kẻ xanh ở chỗ viết câu trả lời. */
export default function QuestionCard({ q, index, total, disabled, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [choice, setChoice] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement>(null);

  useEffect(() => { setText(""); setChoice(null); inputRef.current?.focus(); }, [q.question_id]);

  const answer = q.qtype === "mcq" ? (choice ?? "") : text.trim();
  const submit = () => { if (answer && !disabled) onSubmit(answer); };

  return (
    <article className="qcard" aria-labelledby="q-title">
      <header className="qcard-head">
        <span className="qcard-topic">{q.topic || q.document}</span>
        <span className="qcard-meta">
          Câu {index} / {total} · {typeLabel[q.qtype]} · {levelLabel[q.level]}
        </span>
      </header>

      <h1 id="q-title" className="qcard-question">{q.question}</h1>

      <form onSubmit={(e) => { e.preventDefault(); submit(); }}>
        {q.qtype === "mcq" && q.options && (
          <fieldset className="choices" disabled={disabled}>
            <legend className="sr">Chọn một đáp án</legend>
            {q.options.map((opt) => {
              const letter = opt.charAt(0);
              return (
                <label key={opt} className={`choice${choice === letter ? " is-picked" : ""}`}>
                  <input type="radio" name="choice" value={letter} checked={choice === letter} onChange={() => setChoice(letter)} />
                  <span className="choice-letter">{letter}</span>
                  <span>{opt.slice(3)}</span>
                </label>
              );
            })}
          </fieldset>
        )}

        {q.qtype === "fill_blank" && (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            className="ruled-input" value={text} disabled={disabled} maxLength={200}
            onChange={(e) => setText(e.target.value)} placeholder="Điền vào chỗ trống" aria-label="Đáp án của bạn" autoComplete="off"
          />
        )}

        {(q.qtype === "short_answer" || q.qtype === "scenario") && (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            className="ruled" rows={6} value={text} disabled={disabled} maxLength={2000}
            onChange={(e) => setText(e.target.value)} aria-label="Câu trả lời của bạn"
            placeholder={q.qtype === "scenario" ? "Bạn sẽ làm gì, theo thứ tự nào?" : "Trả lời bằng lời của bạn"}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(); }}
          />
        )}

        <div className="actions">
          <button className="btn" type="submit" disabled={disabled || !answer}>Gửi đáp án</button>
          {(q.qtype === "short_answer" || q.qtype === "scenario") && <span className="hint">Ctrl + Enter để gửi</span>}
        </div>
      </form>
    </article>
  );
}
