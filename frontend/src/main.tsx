import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Box } from "lucide-react";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <main className="auth-layout">
      <div className="auth-panel">
        <div className="brand"><span className="brand-mark"><Box size={21} /></span>Forma AI</div>
        <h1>工业设计工作区</h1>
        <p className="subtle">正在连接工作区。</p>
      </div>
      <div className="auth-visual" role="img" aria-label="原创桌面空气净化器概念设计" />
    </main>
  </StrictMode>,
);
