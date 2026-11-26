import { Activity, Download, RotateCw } from "lucide-react";
import { type ReactNode, useState } from "react";
import { api, assetUrl, dateTime, useAction, useResource } from "../api";
import { type Asset, type Call, type Job, statusNames, taskNames } from "../types";
import { Button, ErrorLine, Loading, Modal } from "../ui";

export function JobStatus({ job }: { job: Job }) {
  const label = job.status === "running" && (job.kind === "generate" || job.kind === "edit") ? "生成中" : statusNames[job.status];
  return <span className={`badge task-status status-${job.status}`}>{label}</span>;
}

export function CallsTable({ calls }: { calls: Call[] }) {
  const labels: Record<string, string> = { running: "请求中", succeeded: "响应成功", failed: "失败", interrupted: "中断" };
  return calls.length ? <div className="table-scroll"><table>
    <thead><tr><th>请求</th><th>状态</th><th>耗时</th><th>供应商记录</th></tr></thead>
    <tbody>{calls.map((call) => <tr key={call.id}>
      <td>{call.operation}<small>第 {call.generation} 次 · {dateTime(call.created_at)}</small></td>
      <td>{labels[call.status] ?? call.status}{call.http_status && <small>HTTP {call.http_status}</small>}</td>
      <td>{call.elapsed_ms === null ? "—" : `${call.elapsed_ms} ms`}</td>
      <td>{call.request_id || "—"}{call.usage && <small>{JSON.stringify(call.usage)}</small>}</td>
    </tr>)}</tbody>
  </table></div> : <p className="subtle">暂无上游调用记录。</p>;
}

export function JobLog({ id, onClose }: { id: string; onClose: () => void }) {
  const current = useResource<Job>(`/jobs/${id}`, 2000);
  return <Modal title="任务与调用记录" onClose={onClose} wide>
    {current.loading && <Loading />}<ErrorLine error={current.error} />
    {current.data && <div className="form-stack">
      <div className="split-row"><span>{dateTime(current.data.created_at)}</span><JobStatus job={current.data} /></div>
      <ErrorLine error={current.data.error ?? undefined} /><CallsTable calls={current.data.calls ?? []} />
    </div>}
  </Modal>;
}

export function RetryJob({ job, refresh }: { job: Job; refresh: () => void }) {
  const action = useAction();
  if (job.status !== "failed") return null;
  return <div className="form-stack">
    <Button busy={action.busy} onClick={() => {
      if (!job.mock && !window.confirm("确认重新向外部服务提交。该操作可能再次计费。")) return;
      void action.run(async () => { await api(`/jobs/${job.id}/retry`, "POST", { ack_external: !job.mock }); refresh(); });
    }}><RotateCw size={15} />重试</Button>
    <ErrorLine error={action.error} />
  </div>;
}

export function JobItem({ job, onPreview, refresh, assetActions, children }: {
  job: Job; onPreview?: (asset: Asset) => void; refresh: () => void; assetActions?: (index: number) => ReactNode; children?: ReactNode;
}) {
  const [log, setLog] = useState(false);
  return <article className="job-item">
    <div className="split-row job-heading">
      <div><strong>{job.kind === "probe_connection" ? "连接测试" : job.kind === "probe_model" ? "能力测试" : taskNames[job.kind]}</strong>
        <small>{dateTime(job.created_at)}{job.mock ? " · Mock" : ""}</small></div>
      <div className="actions"><JobStatus job={job} /><Button variant="ghost" onClick={() => setLog(true)}><Activity size={15} />记录</Button></div>
    </div>
    <ErrorLine error={job.error ?? undefined} />
    {job.result?.message && <p className="subtle">{job.result.message}{job.result.width ? ` · ${job.result.width} × ${job.result.height}` : ""}</p>}
    {!!job.result?.models?.length && <p className="subtle">{job.result.models.join("、")}</p>}
    {job.result?.summary && <div className="notice"><div>{job.result.summary}
      {job.result.uncertainties?.map((item, index) => <p key={index}>· {item}</p>)}</div></div>}
    {job.result?.assets && onPreview && <div className="job-image-grid">
      {job.result.assets.map((asset, index) => <div key={asset.id} className="job-image">
        <button type="button" onClick={() => onPreview(asset)}><img loading="lazy" src={assetUrl(asset.id)} alt={asset.filename} /></button>
        <div className="actions job-image-actions">
          <a className="btn btn-ghost" href={assetUrl(asset.id, true)}><Download size={15} />下载</a>{assetActions?.(index)}
        </div>
      </div>)}
    </div>}
    {children}
    <RetryJob job={job} refresh={refresh} />
    {log && <JobLog id={job.id} onClose={() => setLog(false)} />}
  </article>;
}
