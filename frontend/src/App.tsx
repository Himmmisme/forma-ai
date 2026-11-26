import { Box, Columns2, FolderOpen, History, ImageIcon, Layers3, LayoutDashboard, LogOut, Menu, Moon, Settings, Shield, Sparkles, Star, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, ApiError, message } from "./api";
import { AccountPage, AuthScreen } from "./features/Accounts";
import { AdminPage } from "./features/Admin";
import { AnalysisPage } from "./features/Analysis";
import { AssetLibrary, Overview, ProjectStudio, ProjectsPage } from "./features/Projects";
import { ComparePage, FavoritesPage, HistoryPage, WorkbenchPage } from "./features/Versions";
import { type User, roleNames } from "./types";
import { Brand, Button, ErrorLine, IconButton, Loading } from "./ui";

const navigation = [
  { to: "/", label: "概览", icon: LayoutDashboard },
  { to: "/projects", label: "我的项目", icon: FolderOpen },
  { to: "/design", label: "AI 设计工作台", icon: Sparkles },
  { to: "/history", label: "历史版本", icon: History },
  { to: "/compare", label: "方案对比", icon: Columns2 },
  { to: "/analysis", label: "材料与成本", icon: Layers3 },
  { to: "/assets", label: "素材库", icon: ImageIcon },
  { to: "/favorites", label: "收藏方案", icon: Star },
];

export function App() {
  const [user, setUser] = useState<User | null>();
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(localStorage.getItem("forma-theme") === "dark" ? "dark" : "light");
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("forma-theme", theme);
  }, [theme]);
  useEffect(() => {
    let active = true;
    api<User>("/auth/me").then((value) => { if (active) setUser(value); }).catch((exception) => {
      if (!active) return;
      if (exception instanceof ApiError && exception.status === 401) setUser(null);
      else setError(message(exception));
    });
    return () => { active = false; };
  }, []);
  useEffect(() => { setDrawer(false); window.scrollTo(0, 0); }, [location.pathname]);
  useEffect(() => {
    const expire = () => setUser(null);
    window.addEventListener("forma-session-expired", expire);
    return () => window.removeEventListener("forma-session-expired", expire);
  }, []);

  async function signOut() {
    try { await api("/auth/logout", "POST"); setUser(null); }
    catch (exception) { setError(message(exception)); }
  }

  if (user === undefined) return <div className="startup">
    <Brand />{error ? <><ErrorLine error={error} /><Button onClick={() => window.location.reload()}>重新连接</Button></> : <Loading />}
  </div>;
  if (!user) return <AuthScreen onUser={setUser} />;
  if (user.must_change_password) return <main className="forced-account">
    <div className="split-row"><Brand /><Button variant="ghost" onClick={signOut}>退出登录</Button></div>
    <ErrorLine error={error} /><AccountPage user={user} onUser={setUser} forced />
  </main>;

  const isAdmin = user.role !== "user";
  const section = [...navigation, { to: "/settings", label: "个人设置" }, { to: "/admin", label: "管理后台" }]
    .find(({ to }) => to === location.pathname || (to !== "/" && location.pathname.startsWith(to + "/")));
  return <div className="app-shell">
    <a className="skip-link" href="#workspace">跳到工作区</a>
    {drawer && <button className="drawer-overlay" aria-label="收起导航" onClick={() => setDrawer(false)} />}
    <aside className={`sidebar ${drawer ? "open" : ""}`}>
      <Link className="brand-link" to="/" aria-label="Forma AI 概览"><Brand /></Link>
      <nav aria-label="主要导航">
        <div className="nav-caption">工作区</div>
        {navigation.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === "/"}>
          <Icon size={19} /><span>{label}</span>
        </NavLink>)}
      </nav>
      <nav className="secondary-navigation" aria-label="账户和管理">
        <div className="nav-caption">管理</div>
        {isAdmin && <NavLink to="/admin"><Shield size={19} />管理后台</NavLink>}
        <NavLink to="/settings"><Settings size={19} />个人设置</NavLink>
      </nav>
      <div className="sidebar-footer">
        <span className="avatar">{user.name.slice(0, 1)}</span>
        <div><strong>{user.name}</strong><small>{roleNames[user.role]}</small></div>
        <IconButton title="退出登录" onClick={signOut}><LogOut size={17} /></IconButton>
      </div>
    </aside>
    <div className="main-shell">
      <header className="topbar">
        <IconButton className="menu-btn" title="展开导航" onClick={() => setDrawer(true)}><Menu size={21} /></IconButton>
        <div className="breadcrumb"><Box size={17} /><span>Forma 工作区</span><span className="breadcrumb-divider">/</span><strong>{section?.label ?? "设计工作台"}</strong></div>
        <IconButton title={theme === "dark" ? "切换为浅色主题" : "切换为深色主题"}
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
        </IconButton>
      </header>
      <main className="workspace" id="workspace">
        <ErrorLine error={error} />
        <Routes>
          <Route path="/" element={<Overview user={user} />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectStudio />} />
          <Route path="/design" element={<WorkbenchPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/assets" element={<AssetLibrary />} />
          <Route path="/settings" element={<AccountPage user={user} onUser={setUser} />} />
          <Route path="/admin/*" element={isAdmin ? <AdminPage user={user} /> : <Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  </div>;
}
