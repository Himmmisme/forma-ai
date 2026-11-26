import { DatabaseBackup, Download, History, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api, dateTime, useAction, useResource } from "../api";
import type { Call } from "../types";
import { Button, Empty, ErrorLine, Loading } from "../ui";
import { CallsTable } from "./Jobs";

interface BackupRow { id: string; status: "running" | "succeeded" | "failed"; size: number | null; error: string | null; created_at: string }
interface EventRow { id: string; actor: string | null; action: string; entity_id: string | null; context: Record<string, unknown>; created_at: string }
interface Page<T> { items: T[]; more: boolean }
const events: Record<string, string> = {
  "system.initialized": "实例初始化", "system.settings_saved": "保存系统设置", "auth.login": "登录",
  "auth.password_changed": "修改密码", "user.created": "创建用户", "user.updated": "更新用户",
  "user.password_reset": "重置密码", "project.trashed": "移入回收站", "project.restored": "恢复项目",
  "provider.saved": "保存服务商", "provider.test_queued": "提交 API 测试", "model.saved": "保存模型",
  "binding.saved": "保存任务绑定", "template.created": "创建模板", "template.saved": "保存模板",
  "job.retried": "重试任务", "price.saved": "保存报价", "price.imported": "导入报价", "backup.created": "创建备份",
};

export function SystemPanel() {
  const [area, setArea] = useState<"backup" | "audit" | "calls">("backup");
  const [offset, setOffset] = useState(0);
  const settings = useResource<{ external_enabled: boolean; worker_slots: number }>("/admin/system");
  const resource = useResource<Page<BackupRow>>(`/admin/backups?offset=${offset}`, area === "backup" ? 4000 : 0);
  const audit = useResource<Page<EventRow>>(area === "audit" ? `/admin/audit?offset=${offset}` : null);
  const calls = useResource<Page<Call & { provider: string; kind: string }>>(area === "calls" ? `/admin/calls?offset=${offset}` : null);
  const configure = useAction();
  const backup = useAction();
  const [notice, setNotice] = useState("");
  const shown = area === "backup" ? resource : area === "audit" ? audit : calls;
  const limit = area === "backup" ? 50 : 100;
  const options = [["backup", "整站备份"], ["audit", "系统操作"], ["calls", "API 调用"]] as const;
  return <div className="form-stack">
    <section className="panel form-stack">
      <h2><ShieldCheck size={18} />系统设置</h2>
      {settings.loading && <Loading />}<ErrorLine error={settings.error || configure.error} />
      {settings.data && <div className="split-row"><p className="subtle compact">任务并发槽位 {settings.data.worker_slots} · Mock 模式可独立使用</p>
        <label className="check-row"><input type="checkbox" checked={settings.data.external_enabled} disabled={configure.busy}
          onChange={(event) => {
            const enabled = event.target.checked;
            void configure.run(async () => { await api("/admin/system", "PUT", { external_enabled: enabled }); settings.refresh(); });
          }} />允许外部 API 调用</label></div>}
    </section>
    <section className="panel form-stack">
      <div className="section-heading"><div><h2><History size={18} />系统日志与备份</h2><p>查看受控操作、供应商调用和实例快照。</p></div></div>
      <div className="tabs">{options.map(([key, label]) => <button key={key} className={key === area ? "active" : ""}
        onClick={() => { setArea(key); setOffset(0); }}>{label}</button>)}</div>
      {area === "backup" && <>
        <div className="split-row"><p className="subtle compact">快照包含数据库和图片。离线恢复与密钥卷备份步骤见部署说明。</p>
          <Button variant="primary" busy={backup.busy} onClick={() => void backup.run(async () => {
            setNotice("");
            const row = await api<BackupRow>("/admin/backups", "POST");
            resource.refresh();
            if (row.status === "succeeded") setNotice("完整备份已创建");
          })}><DatabaseBackup size={17} />创建完整备份</Button></div>
        {notice && <div className="notice success" role="status">{notice}</div>}
        <ErrorLine error={backup.error} />
        {!!resource.data?.items.length && <div className="table-scroll"><table>
          <thead><tr><th>创建时间</th><th>状态</th><th>大小</th><th>操作</th></tr></thead>
          <tbody>{resource.data.items.map((row) => <tr key={row.id}>
            <td>{dateTime(row.created_at)}</td>
            <td>{row.status === "succeeded" ? "完成" : row.status === "failed" ? "失败" : "处理中"}{row.error && <small>{row.error}</small>}</td>
            <td>{row.size === null ? "—" : Math.max(.01, row.size / 1048576).toFixed(2) + " MB"}</td>
            <td>{row.status === "succeeded" && <a className="btn btn-secondary" href={`/api/admin/backups/${row.id}/download`}>
              <Download size={16} />下载备份</a>}</td>
          </tr>)}</tbody>
        </table></div>}
      </>}
      {area === "audit" && !!audit.data?.items.length && <div className="table-scroll"><table>
        <thead><tr><th>时间</th><th>操作者</th><th>操作</th><th>记录详情</th></tr></thead>
        <tbody>{audit.data.items.map((event) => <tr key={event.id}>
          <td>{dateTime(event.created_at)}</td><td>{event.actor || "系统"}</td><td>{events[event.action] ?? event.action}</td>
          <td>{event.entity_id || "—"}{Object.keys(event.context).length > 0 && <small>{JSON.stringify(event.context)}</small>}</td>
        </tr>)}</tbody>
      </table></div>}
      {area === "calls" && !!calls.data?.items.length && <CallsTable calls={calls.data.items.map((call) =>
        ({ ...call, operation: `${call.provider} · ${call.operation}` }))} />}
      {shown.loading && <Loading />}<ErrorLine error={shown.error} />
      {shown.data?.items.length === 0 && <Empty title={area === "backup" ? "暂无备份" : "暂无记录"} />}
      {(offset > 0 || shown.data?.more) && <div className="actions pager">
        <Button disabled={!offset} onClick={() => setOffset(offset - limit)}>上一页</Button>
        <Button disabled={!shown.data?.more} onClick={() => setOffset(offset + limit)}>下一页</Button>
      </div>}
    </section>
  </div>;
}
