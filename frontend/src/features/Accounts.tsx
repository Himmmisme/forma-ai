import { Eye, EyeOff, LogIn, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, useAction, useResource } from "../api";
import { type User, roleNames } from "../types";
import { Brand, Button, ErrorLine, Field, Heading, IconButton, Loading } from "../ui";

export function AuthScreen({ onUser }: { onUser: (user: User) => void }) {
  const setup = useResource<{ initialized: boolean; available: boolean }>("/auth/setup");
  const action = useAction();
  const [show, setShow] = useState(false);
  const navigate = useNavigate();
  const firstRun = setup.data?.initialized === false;
  return <main className="auth-layout">
    <section className="auth-panel">
      <Brand />
      <div className="auth-heading">
        <h1>{firstRun ? "初始化工作区" : "登录设计工作区"}</h1>
        <p className="subtle">{firstRun ? "使用部署时生成的令牌创建首个超级管理员。" : "使用管理员分配的账号进入 Forma AI。"}</p>
      </div>
      {setup.loading && <Loading />}
      <ErrorLine error={setup.error} />
      {setup.error && <Button onClick={setup.refresh}>重新连接</Button>}
      {setup.data && <form className="form-stack" onSubmit={(event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        void action.run(async () => {
          onUser(await api<User>(firstRun ? "/auth/setup" : "/auth/login", "POST", values));
          navigate("/", { replace: true });
        });
      }}>
        <ErrorLine error={action.error} />
        {firstRun && !setup.data.available && <ErrorLine error="请部署者配置 APP_SETUP_TOKEN 后重启服务。" />}
        {firstRun && <Field label="初始化令牌"><input name="token" type="password" autoComplete="off" required maxLength={200} /></Field>}
        <Field label="账号" hint={firstRun ? "3–40 位字母、数字、点、下划线或连字符" : undefined}>
          <input name="username" autoComplete="username" required minLength={3} maxLength={40} placeholder="输入账号" />
        </Field>
        {firstRun && <Field label="显示名称"><input name="name" required maxLength={80} placeholder="输入显示名称" /></Field>}
        <Field label="密码" hint={firstRun ? "至少 12 个字符" : undefined}>
          <div className="password-input">
            <input name="password" type={show ? "text" : "password"} autoComplete={firstRun ? "new-password" : "current-password"}
              minLength={firstRun ? 12 : undefined} maxLength={128} required placeholder="输入密码" />
            <IconButton title={show ? "隐藏密码" : "显示密码"} onClick={() => setShow(!show)}>
              {show ? <EyeOff size={18} /> : <Eye size={18} />}
            </IconButton>
          </div>
        </Field>
        <Button className="auth-submit" type="submit" variant="primary" busy={action.busy} disabled={firstRun && !setup.data.available}>
          {firstRun ? <ShieldCheck size={18} /> : <LogIn size={18} />}{firstRun ? "初始化并登录" : "登录"}
        </Button>
      </form>}
      <p className="auth-footer">Forma AI <span>·</span> 工业产品设计</p>
    </section>
    <div className="auth-visual" role="img" aria-label="原创桌面空气净化器概念设计">
      <div className="auth-visual-caption"><span>示例设计</span><strong>桌面空气净化器</strong></div>
    </div>
  </main>;
}

export function AccountPage({ user, onUser, forced = false }: { user: User; onUser: (user: User) => void; forced?: boolean }) {
  const password = useAction();
  const profile = useAction();
  const [notice, setNotice] = useState("");
  return <>
    <Heading title={forced ? "设置你的密码" : "个人设置"} description={forced ? "首次登录或管理员重置后，需要更换临时密码。" : undefined} />
    {notice && <div className="notice success" role="status">{notice}</div>}
    <div className={forced ? "account-grid forced" : "account-grid"}>
      {!forced && <form className="panel form-stack" onSubmit={(event) => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        void profile.run(async () => {
          onUser(await api<User>("/auth/me", "PATCH", values));
          setNotice("个人资料已保存");
        });
      }}>
        <h2>个人资料</h2>
        <div className="account-identity"><span className="avatar">{user.name.slice(0, 1)}</span>
          <div><strong>{user.username}</strong><p className="subtle">{roleNames[user.role]}</p></div>
        </div>
        <Field label="显示名称"><input name="name" required defaultValue={user.name} maxLength={80} /></Field>
        <ErrorLine error={profile.error} />
        <Button type="submit" variant="primary" busy={profile.busy}>保存资料</Button>
      </form>}
      <form className="panel form-stack" onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        if (data.get("password") !== data.get("confirm")) {
          password.setError("两次输入的新密码不同");
          return;
        }
        void password.run(async () => {
          onUser(await api<User>("/auth/password", "POST", { current_password: data.get("current"), password: data.get("password") }));
          form.reset();
          setNotice("密码已修改，其他会话已退出");
        });
      }}>
        <h2>修改密码</h2>
        <Field label="当前密码"><input name="current" type="password" autoComplete="current-password" required /></Field>
        <Field label="新密码" hint="至少 12 个字符"><input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></Field>
        <Field label="确认新密码"><input name="confirm" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></Field>
        <ErrorLine error={password.error} />
        <Button type="submit" variant="primary" busy={password.busy}>{forced ? "保存并进入工作区" : "修改密码"}</Button>
      </form>
    </div>
  </>;
}
