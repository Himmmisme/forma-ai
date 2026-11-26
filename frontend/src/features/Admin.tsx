import { KeyRound, PencilLine, UserPlus, UsersRound } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, dateTime, useAction, useResource } from "../api";
import { type User, roleNames } from "../types";
import { Button, Empty, ErrorLine, Field, Heading, IconButton, Loading, Modal } from "../ui";
import { AISettings, TemplatesPanel } from "./AISettings";
import { PricesPanel } from "./Prices";

export function AdminPage({ user }: { user: User }) {
  const [params, setParams] = useSearchParams();
  const area = params.get("area") ?? "users";
  const sections = [["users", "用户管理"], ["templates", "提示词模板"], ["prices", "材料价格库"],
    ...(user.role === "superadmin" ? [["ai", "API 服务商与模型"]] : [])];
  return <><Heading title="管理后台" />
    <div className="tabs">{sections.map(([key, label]) => <button key={key} className={area === key ? "active" : ""}
      onClick={() => setParams({ area: key })}>{label}</button>)}</div>
    {area === "ai" && user.role === "superadmin" ? <AISettings /> : area === "templates" ? <TemplatesPanel /> :
      area === "prices" ? <PricesPanel /> : <UsersPanel actor={user} />}
  </>;
}

function UsersPanel({ actor }: { actor: User }) {
  const [offset, setOffset] = useState(0);
  const users = useResource<User[]>(`/admin/users?offset=${offset}`);
  const [dialog, setDialog] = useState<{ type: "create" } | { type: "edit" | "reset"; user: User }>();
  return <section className="panel">
    <div className="section-heading"><div><h2>用户管理</h2><p>为团队分配账号、角色与访问权限。</p></div>
      <Button variant="primary" onClick={() => setDialog({ type: "create" })}><UserPlus size={17} />创建用户</Button>
    </div>
    <ErrorLine error={users.error} />
    {users.loading && <Loading />}
    {users.data?.length === 0 && <Empty title="本页没有用户" icon={<UsersRound size={23} />} />}
    {!!users.data?.length && <div className="table-scroll"><table>
      <thead><tr><th>用户</th><th>角色</th><th>状态</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody>{users.data.map((user) => <tr key={user.id}>
        <td><strong>{user.name}</strong><small>{user.username}</small></td><td>{roleNames[user.role]}</td>
        <td><span className={`badge ${user.enabled ? "positive" : ""}`}>{user.enabled ? user.must_change_password ? "待修改密码" : "启用" : "禁用"}</span></td>
        <td>{dateTime(user.created_at)}</td>
        <td>{user.id !== actor.id && <div className="actions">
          <IconButton title={`编辑 ${user.username}`} onClick={() => setDialog({ type: "edit", user })}><PencilLine size={17} /></IconButton>
          <IconButton title={`重置 ${user.username} 的密码`} onClick={() => setDialog({ type: "reset", user })}><KeyRound size={17} /></IconButton>
        </div>}</td>
      </tr>)}</tbody>
    </table></div>}
    {(offset > 0 || users.data?.length === 200) && <div className="actions pager">
      <Button onClick={() => setOffset(offset - 200)} disabled={!offset}>上一页</Button>
      <Button onClick={() => setOffset(offset + 200)} disabled={users.data?.length !== 200}>下一页</Button>
    </div>}
    {dialog && <UserEditor actor={actor} mode={dialog.type} target={"user" in dialog ? dialog.user : undefined}
      onClose={() => setDialog(undefined)} onSaved={() => { setDialog(undefined); users.refresh(); }} />}
  </section>;
}

function UserEditor({ actor, mode, target, onClose, onSaved }: { actor: User; mode: "create" | "edit" | "reset"; target?: User; onClose: () => void; onSaved: () => void }) {
  const action = useAction();
  const title = mode === "create" ? "创建用户" : mode === "edit" ? "编辑用户" : "重置密码";
  return <Modal title={title} onClose={onClose}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      void action.run(async () => {
        if (mode === "create") await api("/admin/users", "POST", Object.fromEntries(form));
        else if (mode === "edit") await api(`/admin/users/${target!.id}`, "PATCH", {
          name: form.get("name"), enabled: form.get("enabled") === "true",
          ...(actor.role === "superadmin" && { role: form.get("role") }),
        });
        else await api(`/admin/users/${target!.id}/password`, "POST", { password: form.get("password") });
        onSaved();
      });
    }}>
      {mode === "create" && <Field label="账号"><input name="username" minLength={3} maxLength={40} required pattern={"[a-zA-Z0-9_.\\-]+"} /></Field>}
      {mode !== "reset" && <Field label="显示名称"><input name="name" defaultValue={target?.name} maxLength={80} required /></Field>}
      {mode !== "edit" && <Field label="临时密码" hint="至少 12 个字符。用户下一次登录需更换密码。">
        <input name="password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required />
      </Field>}
      {mode !== "reset" && actor.role === "superadmin" && <Field label="角色"><select name="role" defaultValue={target?.role ?? "user"}>
        {Object.entries(roleNames).map(([role, name]) => <option key={role} value={role}>{name}</option>)}
      </select></Field>}
      {mode === "edit" && <Field label="状态"><select name="enabled" defaultValue={String(target?.enabled)}>
        <option value="true">启用</option><option value="false">禁用</option>
      </select></Field>}
      <ErrorLine error={action.error} />
      <div className="actions dialog-actions"><Button onClick={onClose}>取消</Button>
        <Button type="submit" variant="primary" busy={action.busy}>{title}</Button></div>
    </form>
  </Modal>;
}
