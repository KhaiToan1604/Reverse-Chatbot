// Điểm vào của giao diện: gắn <App /> vào #root. HashRouter (đường dẫn dạng /#/quiz/1) giúp backend
// phục vụ file tĩnh mà không cần cấu hình chuyển hướng cho từng đường dẫn.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);
