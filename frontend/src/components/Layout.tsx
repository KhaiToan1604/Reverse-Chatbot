import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
import type { User } from "../types";

export default function Layout({ user, onLogout, children }: { user: User | null; onLogout: () => void; children: ReactNode }) {
  return (
    <>
      <header className="topbar">
        <div className="wrap topbar-in">
          <NavLink to="/" className="brand">
            <span className="brand-mark" aria-hidden="true" />
            Reverse Chatbot
          </NavLink>
          <nav aria-label="Điều hướng chính">
            <NavLink to="/" end>Học</NavLink>
            <NavLink to="/progress">Tiến độ</NavLink>
            <NavLink to="/admin">Quản trị</NavLink>
          </nav>
          {user && (
            <div className="who">
              <span>{user.display_name}</span>
              <button className="link" onClick={onLogout}>Đổi người dùng</button>
            </div>
          )}
        </div>
      </header>
      <main className="wrap">{children}</main>
    </>
  );
}
