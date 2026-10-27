import type { ReactNode } from "react";
import { useEffect, useState } from "react";

export function Busy({ children }: { children: ReactNode }) {
  return (
    <div className="busy" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {children}
    </div>
  );
}

export function ErrorNote({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  if (!error) return null;
  return (
    <div className="note note-error" role="alert">
      <span>{error}</span>
      {onRetry && <button className="link" onClick={onRetry}>Thử lại</button>}
    </div>
  );
}

export function Meter({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div className="meter" role="img" aria-label={`${label}: ${pct}%`}>
      <div className="meter-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

export const levelLabel = { recall: "Nhớ thông tin", apply: "Vận dụng" } as const;
export const typeLabel = { mcq: "Trắc nghiệm", fill_blank: "Điền khuyết", short_answer: "Trả lời ngắn", scenario: "Tình huống" } as const;

/** Hook nạp dữ liệu có trạng thái loading/error và nút thử lại. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fn().then((d) => live && setData(d)).catch((e: Error) => live && setError(e.message)).finally(() => live && setLoading(false));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData };
}

export function fmtDue(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso + "Z");
  const hours = (d.getTime() - Date.now()) / 36e5;
  if (hours <= 0.05) return "ôn lại ngay";
  if (hours < 24) return `ôn lại sau ${Math.ceil(hours)} giờ`;
  return `ôn lại sau ${Math.round(hours / 24)} ngày`;
}
