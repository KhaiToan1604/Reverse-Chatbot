// Trạng thái "người học hiện tại": chỉ lưu {id, display_name} ở localStorage của trình duyệt (chưa có đăng nhập).
import { useCallback, useState } from "react";
import type { User } from "./types";

const KEY = "rc_user";

// Đọc an toàn: localStorage có thể bị chặn (chế độ riêng tư) hoặc chứa dữ liệu hỏng -> coi như chưa có người dùng.
function read(): User | null {
  try { const v = localStorage.getItem(KEY); return v ? (JSON.parse(v) as User) : null; } catch { return null; }
}

/** Người học hiện tại, lưu ở trình duyệt (chưa có đăng nhập thật — xem README backend). */
export function useUser() {
  const [user, setUserState] = useState<User | null>(read);
  const setUser = useCallback((u: User | null) => {
    try { u ? localStorage.setItem(KEY, JSON.stringify(u)) : localStorage.removeItem(KEY); } catch { /* bỏ qua */ }
    setUserState(u);
  }, []);
  return { user, setUser };
}
