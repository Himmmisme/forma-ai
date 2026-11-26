import { Columns2, Download, GitBranch, History, ListTree, Star } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, assetUrl, dateTime, useAction, useResource } from "../api";
import { type Asset, type Version, type VersionDetail, type VersionList, statusNames } from "../types";
import { Button, Empty, ErrorLine, Field, Heading, IconButton, Loading, Modal, Preview } from "../ui";
import { CallsTable } from "./Jobs";
import { ProjectSelect } from "./Projects";

export function versionNumber(number: number) {
  return "V" + String(number).padStart(3, "0");
}

export function WorkbenchPage() {
  const [id, setId] = useState("");
  return <><Heading title="AI 设计工作台" description="选择项目后上传产品图片，并生成新的工业设计方案。" />
    <div className="panel form-stack"><ProjectSelect selected={id} onSelect={setId} />
      <div className="actions">{id && <Link className="btn btn-primary" to={`/projects/${id}`}>打开工作台</Link>}
        <Link className="btn btn-secondary" to="/projects">管理项目</Link></div>
    </div>
  </>;
}

export function HistoryPage() {
  const [params, setParams] = useSearchParams();
  const project = params.get("project") ?? "";
  return <><Heading title="历史版本" description="查看生成参数、追溯迭代关系，或从任意已生成版本开始修改。" />
    <div className="toolbar"><ProjectSelect selected={project} onSelect={(id) => setParams(id ? { project: id } : {})} />
      {project && <Link className="btn btn-secondary" to={`/projects/${project}`}>打开工作台</Link>}</div>
    {project ? <HistoryPanel key={project} project={project} full /> :
      <div className="panel"><Empty title="选择项目查看版本" icon={<History size={25} />} /></div>}
  </>;
}

export function HistoryPanel({ project, full = false }: { project: string; full?: boolean }) {
  const [offset, setOffset] = useState(0);
  const limit = full ? 24 : 6;
  const resource = useResource<VersionList>(`/projects/${project}/versions?limit=${limit}&offset=${offset}`, full ? 0 : 3500);
  return <section className={full ? "form-stack" : "panel form-stack"}>
    {!full && <div className="split-row"><h2><History size={17} />历史版本</h2>
      <Link className="btn btn-ghost" to={`/history?project=${project}`}>查看全部</Link></div>}
    {resource.loading && <Loading />}<ErrorLine error={resource.error} />
    {resource.data?.items.length === 0 && <Empty title="还没有版本" icon={<GitBranch size={23} />} />}
    <div className="project-grid">{resource.data?.items.map((item) => <VersionCard key={item.id} version={item} refresh={resource.refresh} />)}</div>
    {(offset > 0 || resource.data?.more) && <div className="actions pager">
      <Button onClick={() => setOffset(offset - limit)} disabled={!offset}>上一页</Button>
      <Button onClick={() => setOffset(offset + limit)} disabled={!resource.data?.more}>下一页</Button>
    </div>}
  </section>;
}

export function FavoritesPage() {
  const [offset, setOffset] = useState(0);
  const resource = useResource<VersionList>(`/favorites?offset=${offset}`);
  return <><Heading title="收藏方案" description="随时回看你收藏的设计成果。" />
    {resource.loading && <Loading />}<ErrorLine error={resource.error} />
    {resource.data?.items.length === 0 && <div className="panel"><Empty title="还没有收藏方案" description="在历史版本中点击星标，即可将方案收录在此。" icon={<Star size={24} />} /></div>}
    <div className="project-grid">{resource.data?.items.map((item) => <VersionCard key={item.id} version={item} refresh={resource.refresh} />)}</div>
    {(offset > 0 || resource.data?.more) && <div className="actions pager">
      <Button onClick={() => setOffset(offset - 24)} disabled={!offset}>上一页</Button>
      <Button onClick={() => setOffset(offset + 24)} disabled={!resource.data?.more}>下一页</Button>
    </div>}
  </>;
}

function VersionCard({ version, refresh }: { version: Version; refresh: () => void }) {
  const [details, setDetails] = useState(false);
  const [preview, setPreview] = useState(false);
  const action = useAction();
  return <article className="project-card">
    {version.asset ? <button type="button" className="project-cover" onClick={() => setPreview(true)} aria-label={`预览 ${versionNumber(version.number)}`}>
      <img src={assetUrl(version.asset.id)} loading="lazy" alt={`${versionNumber(version.number)} 设计成果`} />
    </button> : <div className="project-cover"><History size={27} /></div>}
    <div className="project-card-copy">
      <div className="split-row"><h3>{versionNumber(version.number)}{version.project_name ? ` · ${version.project_name}` : ""}</h3>
        {version.asset && <IconButton title={version.favorite ? "取消收藏方案" : "收藏方案"} disabled={action.busy}
          onClick={() => void action.run(async () => {
            await api(`/versions/${version.id}`, "PATCH", { favorite: !version.favorite }); refresh();
          })}><Star size={17} fill={version.favorite ? "currentColor" : "none"} /></IconButton>}</div>
      <p className="project-meta">{version.direction} · {version.level}{version.mock ? " · Mock" : ""}</p>
      <div className="split-row project-meta"><span>{statusNames[version.status]}</span><span>{dateTime(version.created_at)}</span></div>
      <div className="actions">
        <Button variant="ghost" onClick={() => setDetails(true)}><ListTree size={15} />参数</Button>
        {version.asset && <VersionLinks id={version.id} project={version.project_id} />}
      </div>
      <ErrorLine error={action.error} />
    </div>
    {details && <VersionParams id={version.id} onClose={() => setDetails(false)} />}
    {preview && version.asset && <Preview asset={version.asset} onClose={() => setPreview(false)} />}
  </article>;
}

export function VersionLinks({ id, project }: { id: string; project: string }) {
  return <>
    <Link className="btn btn-ghost" to={`/projects/${project}?parent=${id}#design-config`}><GitBranch size={15} />继续修改</Link>
    <Link className="btn btn-ghost" to={`/compare?project=${project}&right=${id}`}><Columns2 size={15} />对比</Link>
  </>;
}

export function VersionParams({ id, onClose }: { id: string; onClose: () => void }) {
  const resource = useResource<VersionDetail>(`/versions/${id}`);
  const [parent, setParent] = useState<string>();
  const [preview, setPreview] = useState<Asset>();
  const version = resource.data;
  const config = version?.configuration;
  return <Modal title={version ? `${versionNumber(version.number)} 生成参数` : "生成参数"} onClose={onClose} wide>
    {resource.loading && <Loading />}<ErrorLine error={resource.error} />
    {version && config && <div className="form-stack">
      <div className="split-row"><strong>{version.project_name}</strong><span className="badge">{statusNames[version.status]}</span></div>
      <div className="metadata-grid">
        <div><small>创建者 / 时间</small>{version.author} · {dateTime(version.created_at)}</div>
        <div><small>父版本</small>{version.parent_id && version.parent_number ?
          <Button onClick={() => setParent(version.parent_id!)}>{versionNumber(version.parent_number)}</Button> : "初始版本"}</div>
        <div><small>服务商 / 模型</small>{config.provider.name} · {config.model.model_code}</div>
        <div><small>输出</small>{config.output.ratio} · {config.output.size} · {config.output.count} 张</div>
        <div><small>主方向 / 修订</small>{config.templates.main.name} · r{config.templates.main.revision}</div>
        <div><small>辅助方向 / 修订</small>{config.templates.auxiliary.map((row) => `${row.name} r${row.revision}`).join("、") || "—"}</div>
        <div><small>重构档位 / 修订</small>{config.templates.level.name} · r{config.templates.level.revision}</div>
        <div><small>基础提示词 / 视角 / 背景</small>v{config.templates.base_revision} · {config.output.view} · {config.output.background}</div>
      </div>
      <div className="asset-thumbnails">{[
        ...version.originals.map((asset) => ({ asset, label: "原图" })),
        ...version.references.map((asset) => ({ asset, label: "参考图" })),
        ...(version.iteration ? [{ asset: version.iteration, label: "迭代输入" }] : []),
      ].map(({ asset, label }) => <div className="thumbnail" key={asset.id}>
        <button type="button" onClick={() => setPreview(asset)}><img src={assetUrl(asset.id)} alt={asset.filename} /></button>
        <span className="badge">{label}</span>
      </div>)}</div>
      {Object.entries({ "原始需求": config.raw, "优化需求": config.optimized, "最终需求": config.final,
        "保留约束": config.constraints, "实际发送提示词": config.prompt }).map(([label, value]) =>
        <details key={label} open={label === "实际发送提示词"}><summary>{label}</summary><pre className="text-preview">{value || "—"}</pre></details>)}
      <h3>调用记录</h3><ErrorLine error={version.job.error ?? undefined} /><CallsTable calls={version.job.calls ?? []} />
      {version.asset && <div className="actions">
        <a className="btn btn-secondary" href={assetUrl(version.asset.id, true)}><Download size={16} />下载原始成果</a>
      </div>}
    </div>}
    {parent && <VersionParams id={parent} onClose={() => setParent(undefined)} />}
    {preview && <Preview asset={preview} onClose={() => setPreview(undefined)} />}
  </Modal>;
}

interface CompareOption { id: string; label: string; asset: Asset }
export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const project = params.get("project") ?? "";
  const options = useResource<CompareOption[]>(project ? `/projects/${project}/comparison-options` : null);
  const [preview, setPreview] = useState<Asset>();
  const choices = options.data ?? [];
  const left = choices.find((row) => row.id === params.get("left")) ?? choices[0];
  const right = choices.find((row) => row.id === params.get("right")) ?? [...choices].reverse().find((row) => row.id !== left?.id);
  return <><Heading title="方案对比" description="并排查看设计版本，或将设计成果与产品原图对照。" />
    <div className="toolbar"><ProjectSelect selected={project} onSelect={(value) => setParams(value ? { project: value } : {})} /></div>
    {options.loading && <Loading />}<ErrorLine error={options.error} />
    {!choices.length && !options.loading && <div className="panel"><Empty icon={<Columns2 size={26} />}
      title={project ? "没有可对比的图片" : "选择项目开始对比"} /></div>}
    {!!choices.length && <div className="compare-grid">{[["left", left], ["right", right]].map(([side, item]) => {
      const key = side as string;
      const chosen = item as CompareOption | undefined;
      return <section className="panel form-stack" key={key}>
        <Field label={key === "left" ? "左侧方案" : "右侧方案"}><select value={chosen?.id ?? ""} onChange={(event) => {
          const next = new URLSearchParams(params); next.set(key, event.target.value); setParams(next);
        }}>
          {!chosen && <option value="">选择图片</option>}
          {choices.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
        </select></Field>
        {chosen ? <button type="button" className="compare-image" onClick={() => setPreview(chosen.asset)}>
          <img src={assetUrl(chosen.asset.id)} alt={chosen.label} /></button> : <Empty title="至少需要两张图片" />}
        {chosen && <span className="subtle compact">{chosen.asset.width} × {chosen.asset.height}</span>}
      </section>;
    })}</div>}
    {preview && <Preview asset={preview} onClose={() => setPreview(undefined)} />}
  </>;
}
