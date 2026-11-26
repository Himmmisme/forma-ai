import { Activity, Archive, Box, Download, FolderOpen, ImageIcon, PencilLine, Plus, Search, Sparkles, Star, Trash2, Upload } from "lucide-react";
import { useId, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, assetUrl, dateTime, useAction, useResource } from "../api";
import type { Asset, Dashboard, Project, ProjectList, User } from "../types";
import { Button, Empty, ErrorLine, Field, Heading, IconButton, Loading, Modal, Preview } from "../ui";
import { DesignPanel } from "./Design";
import { HistoryPanel } from "./Versions";

export function Overview({ user }: { user: User }) {
  const router = useNavigate();
  const overview = useResource<Dashboard>("/dashboard", 8000);
  const demo = useAction();
  const [creating, setCreating] = useState(false);
  const stats = [
    { name: "进行中项目", number: overview.data?.projects, icon: FolderOpen },
    { name: "已生成版本", number: overview.data?.versions, icon: ImageIcon },
    { name: "进行中任务", number: overview.data?.running, icon: Activity },
  ];
  return <>
    <Heading title="工作台概览" description={`${user.name}，欢迎进入你的工业设计工作区。`} />
    <section className="overview-hero">
      <img src="/forma-product.webp" alt="桌面空气净化器概念设计" />
      <div className="hero-content">
        <h2>从产品原图出发，<br />探索下一版设计。</h2>
        <p>在同一个项目中管理素材、生成设计版本，并评估材料与成本。</p>
        <div className="actions">
          <Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} />创建项目</Button>
          <Button variant="ghost" busy={demo.busy} onClick={() => void demo.run(async () => {
            const project = await api<Project>("/projects/demo", "POST");
            router(`/projects/${project.id}`);
          })}><Sparkles size={17} />试用示例</Button>
        </div>
        <ErrorLine error={demo.error} />
      </div>
    </section>
    <ErrorLine error={overview.error} />
    <div className="stats-grid">
      {stats.map(({ name, number, icon: Icon }) => <div className="stat-card" key={name}>
        <span className="stat-icon"><Icon size={21} /></span><div><strong>{number ?? "—"}</strong><p>{name}</p></div>
      </div>)}
    </div>
    <section>
      <div className="section-heading"><div><h2>最近项目</h2><p>继续查看或编辑你的设计项目。</p></div>
        <Link className="btn btn-secondary" to="/projects">所有项目</Link>
      </div>
      {overview.loading && <Loading />}
      {overview.data?.recent.length === 0 && <div className="panel"><Empty title="还没有项目" description="创建项目后，可以上传原图并开始设计。"
        icon={<FolderOpen size={24} />} /></div>}
      <div className="project-grid">{overview.data?.recent.map((project) => <ProjectCard key={project.id} project={project} refresh={overview.refresh} />)}</div>
    </section>
    {creating && <ProjectEditor onClose={() => setCreating(false)} onSaved={(project) => router(`/projects/${project.id}`)} />}
  </>;
}

function ProjectCard({ project, refresh }: { project: Project; refresh: () => void }) {
  const action = useAction();
  return <article className="project-card">
    {project.deleted_at ? <div className="project-cover"><Archive size={32} /></div> :
      <Link className="project-cover" to={`/projects/${project.id}`} aria-label={`打开 ${project.name}`}>
        {project.cover_id ? <img src={assetUrl(project.cover_id)} alt="" loading="lazy" /> : <Box size={34} />}
      </Link>}
    <div className="project-card-copy">
      <div className="split-row">
        {project.deleted_at ? <h3>{project.name}</h3> : <Link to={`/projects/${project.id}`}><h3>{project.name}</h3></Link>}
        {!project.deleted_at && <IconButton title={project.favorite ? "取消收藏项目" : "收藏项目"} disabled={action.busy}
          onClick={() => void action.run(async () => {
            await api(`/projects/${project.id}`, "PATCH", { favorite: !project.favorite });
            refresh();
          })}><Star size={18} fill={project.favorite ? "currentColor" : "none"} /></IconButton>}
      </div>
      {project.description && <p className="project-description">{project.description}</p>}
      <div className="split-row project-meta"><span>{project.version_count} 个版本</span><span>{dateTime(project.updated_at)}</span></div>
      <ErrorLine error={action.error} />
      {project.deleted_at && <Button busy={action.busy} onClick={() => void action.run(async () => {
        await api(`/projects/${project.id}/restore`, "POST"); refresh();
      })}>恢复项目</Button>}
    </div>
  </article>;
}

export function ProjectsPage() {
  const router = useNavigate();
  const [status, setStatus] = useState("active");
  const [search, setSearch] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const query = new URLSearchParams({ status, q: search, favorite: String(favorite), offset: String(offset), limit: "24" });
  const results = useResource<ProjectList>(`/projects?${query}`);
  return <>
    <Heading title="我的项目" description="搜索、整理并继续你的产品设计。"
      actions={<Button variant="primary" onClick={() => setCreating(true)}><Plus size={18} />创建项目</Button>} />
    <div className="toolbar">
      <div className="tabs" aria-label="项目状态">
        {[["active", "进行中"], ["archived", "已归档"], ["trash", "回收站"]].map(([id, label]) =>
          <button key={id} className={status === id ? "active" : ""} aria-pressed={status === id}
            onClick={() => { setStatus(id); setOffset(0); }}>{label}</button>)}
      </div>
      <div className="actions">
        <label className="search-input"><Search size={17} /><input aria-label="搜索项目" placeholder="搜索项目" value={search}
          onChange={(event) => { setSearch(event.target.value); setOffset(0); }} maxLength={120} /></label>
        <Button className={favorite ? "selected" : ""} aria-pressed={favorite} onClick={() => { setFavorite(!favorite); setOffset(0); }}>
          <Star size={16} />仅收藏</Button>
      </div>
    </div>
    <ErrorLine error={results.error} />
    {results.loading && <Loading />}
    {results.data?.items.length === 0 && <div className="panel"><Empty title="没有符合条件的项目" icon={<FolderOpen size={25} />} /></div>}
    <div className="project-grid">{results.data?.items.map((project) => <ProjectCard key={project.id} project={project} refresh={results.refresh} />)}</div>
    {(offset > 0 || results.data?.more) && <div className="actions pager">
      <Button onClick={() => setOffset(Math.max(0, offset - 24))} disabled={!offset}>上一页</Button>
      <Button onClick={() => setOffset(offset + 24)} disabled={!results.data?.more}>下一页</Button>
    </div>}
    {creating && <ProjectEditor onClose={() => setCreating(false)} onSaved={(project) => router(`/projects/${project.id}`)} />}
  </>;
}

function ProjectEditor({ project, assets = [], onClose, onSaved }: { project?: Project; assets?: Asset[]; onClose: () => void; onSaved: (value: Project) => void }) {
  const action = useAction();
  return <Modal title={project ? "编辑项目" : "创建项目"} onClose={onClose}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const values = { name: form.get("name"), description: form.get("description"),
        ...(project && { cover_id: form.get("cover_id") || null }) };
      void action.run(async () => {
        onSaved(await api<Project>(project ? `/projects/${project.id}` : "/projects", project ? "PATCH" : "POST", values));
      });
    }}>
      <Field label="项目名称"><input name="name" required maxLength={120} defaultValue={project?.name} placeholder="例如 桌面空气净化器" /></Field>
      <Field label="项目描述"><textarea name="description" maxLength={4000} rows={4} defaultValue={project?.description} /></Field>
      {project && <Field label="封面"><select name="cover_id" defaultValue={project.cover_id ?? ""}>
        <option value="">无封面</option>{assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.filename}</option>)}
      </select></Field>}
      <ErrorLine error={action.error} />
      <div className="actions dialog-actions"><Button onClick={onClose}>取消</Button>
        <Button type="submit" variant="primary" busy={action.busy}>{project ? "保存" : "创建并进入工作台"}</Button></div>
    </form>
  </Modal>;
}

export function ProjectStudio() {
  const { projectId } = useParams();
  const project = useResource<Project>(`/projects/${projectId}`);
  const assets = useResource<Asset[]>(project.data ? `/projects/${projectId}/assets` : null);
  if (!project.data) return <><ErrorLine error={project.error} />{project.loading && <Loading />}</>;
  return <StudioDetail key={project.data.id} project={project.data} assets={assets.data ?? []} onChange={() => { project.refresh(); assets.refresh(); }} />;
}

function StudioDetail({ project, assets, onChange }: { project: Project; assets: Asset[]; onChange: () => void }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const action = useAction();
  const [modal, setModal] = useState<"edit" | "trash">();
  const [preview, setPreview] = useState<Asset>();
  return <>
    <Heading title={project.name} description={project.description || "AI 设计工作台"}
      actions={<>
        <a className="btn btn-secondary" href={`/api/projects/${project.id}/export`} target="_blank" rel="noreferrer"><Download size={16} />导出项目</a>
        <Button onClick={() => setModal("edit")}><PencilLine size={16} />编辑项目</Button>
        <Button busy={action.busy} onClick={() => void action.run(async () => {
          await api(`/projects/${project.id}`, "PATCH", { archived: !project.archived }); onChange();
        })}><Archive size={16} />{project.archived ? "取消归档" : "归档"}</Button>
        <IconButton title="移入回收站" onClick={() => setModal("trash")}><Trash2 size={17} /></IconButton>
      </>} />
    <ErrorLine error={action.error} />
    {project.archived && <div className="notice">项目已归档。取消归档后可以添加素材。</div>}
    <DesignPanel project={project} assets={assets} onPreview={setPreview} parentId={params.get("parent") ?? undefined}
      clearParent={() => setParams({})} sources={<>
        <InputAssets label="产品原图" hint="上传产品的不同角度，用于识别功能区和整体形态。"
          kind="original" project={project} assets={assets} onChange={onChange} onPreview={setPreview} />
        <InputAssets label="设计参考图" hint="可选。用来参考材质、色彩或设计语言。"
          kind="reference" project={project} assets={assets} onChange={onChange} onPreview={setPreview} />
      </>} />
    <HistoryPanel project={project.id} />
    {modal === "edit" && <ProjectEditor project={project} assets={assets} onClose={() => setModal(undefined)}
      onSaved={() => { setModal(undefined); onChange(); }} />}
    {modal === "trash" && <Modal title="移入回收站" onClose={() => setModal(undefined)}>
      <div className="form-stack"><p>将「{project.name}」移入回收站。之后可以在我的项目中恢复。</p>
        <ErrorLine error={action.error} /><div className="actions dialog-actions">
          <Button onClick={() => setModal(undefined)}>取消</Button>
          <Button variant="danger" busy={action.busy} onClick={() => void action.run(async () => {
            await api(`/projects/${project.id}`, "DELETE"); navigate("/projects");
          })}>移入回收站</Button>
        </div>
      </div>
    </Modal>}
    {preview && <Preview asset={preview} onClose={() => setPreview(undefined)} />}
  </>;
}

export function InputAssets({ label, hint, kind, project, assets, onChange, onPreview }: {
  label: string; hint: string; kind: "original" | "reference" | "cover"; project: Project; assets: Asset[];
  onChange: () => void; onPreview: (image: Asset) => void;
}) {
  const inputId = useId();
  const action = useAction();
  const [drag, setDrag] = useState(false);
  function add(files: File[]) {
    if (project.archived || !files.length || action.busy) return;
    void action.run(async () => {
      try {
        for (const file of files) {
          const data = new FormData();
          data.append("file", file, file.name || "粘贴图片.png");
          await api(`/projects/${project.id}/assets?kind=${kind}`, "POST", data);
        }
      } finally { onChange(); }
    });
  }
  const list = assets.filter((asset) => asset.kind === kind);
  return <section className="panel input-assets">
    <h2>{label}</h2><p className="subtle">{hint}</p>
    {!!list.length && <div className="asset-thumbnails">{list.map((asset) => <div className="thumbnail" key={asset.id}>
      <button type="button" aria-label={`预览 ${asset.filename}`} onClick={() => onPreview(asset)}><img src={assetUrl(asset.id)} alt={asset.filename} /></button>
      {!project.archived && <IconButton title={`移除 ${asset.filename}`} disabled={action.busy} onClick={() => void action.run(async () => {
        await api(`/assets/${asset.id}`, "DELETE"); onChange();
      })}><Trash2 size={14} /></IconButton>}
    </div>)}</div>}
    {!project.archived && <div className={`dropzone ${drag ? "drag" : ""}`} tabIndex={0}
      onDragOver={(event) => { event.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
      onDrop={(event) => { event.preventDefault(); setDrag(false); add(Array.from(event.dataTransfer.files)); }}
      onPaste={(event) => {
        const files = Array.from(event.clipboardData.files);
        if (files.length) { event.preventDefault(); add(files); }
      }}>
      <Upload size={18} />
      <label htmlFor={inputId}>{action.busy ? "正在处理图片…" : "选择、拖拽或粘贴图片"}</label>
      <input className="sr-only" id={inputId} aria-label={`上传${label}`} type="file" multiple={kind !== "cover"}
        accept="image/png,image/jpeg,image/webp" disabled={action.busy}
        onChange={(event) => { add(Array.from(event.target.files ?? [])); event.target.value = ""; }} />
      <small>PNG、JPEG、WebP · 每张 ≤ 12 MB</small>
    </div>}
    <ErrorLine error={action.error} />
  </section>;
}

export function ProjectSelect({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const projects = useResource<ProjectList>("/projects?status=all&limit=100");
  return <><Field label="选择项目"><select value={selected} onChange={(event) => onSelect(event.target.value)}>
    <option value="">请选择</option>
    {projects.data?.items.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
  </select></Field><ErrorLine error={projects.error} /></>;
}

export function AssetLibrary() {
  const [params, setParams] = useSearchParams();
  const id = params.get("project") ?? "";
  const [filter, setFilter] = useState("all");
  const [preview, setPreview] = useState<Asset>();
  const project = useResource<Project>(id ? `/projects/${id}` : null);
  const assets = useResource<Asset[]>(id ? `/projects/${id}/assets` : null);
  const items = assets.data?.filter((asset) => filter === "all" || asset.kind === filter) ?? [];
  const kindNames = { original: "原图", reference: "参考图", cover: "封面", result: "成果" };
  return <>
    <Heading title="素材库" description="按项目查找原图、参考图及设计成果。" />
    <div className="toolbar">
      <ProjectSelect selected={id} onSelect={(next) => setParams(next ? { project: next } : {})} />
      <Field label="类型"><select value={filter} onChange={(event) => setFilter(event.target.value)}>
        <option value="all">全部素材</option>
        {Object.entries(kindNames).map(([kind, label]) => <option key={kind} value={kind}>{label}</option>)}
      </select></Field>
    </div>
    <ErrorLine error={assets.error || project.error} />
    {assets.loading && <Loading />}
    {!items.length && !assets.loading && <div className="panel"><Empty title={id ? "没有可显示的素材" : "选择项目查看素材"} /></div>}
    <div className="project-grid">{items.map((asset) => <article className="project-card" key={asset.id}>
      <button className="project-cover" type="button" onClick={() => setPreview(asset)}><img src={assetUrl(asset.id)} alt={asset.filename} loading="lazy" /></button>
      <div className="project-card-copy"><div className="split-row"><strong className="ellipsize">{asset.filename}</strong><span className="badge">{kindNames[asset.kind]}</span></div>
        <div className="project-meta">{asset.width} × {asset.height}</div></div>
    </article>)}</div>
    {project.data && <InputAssets label="项目封面" hint="上传新图片并将其设置为项目封面。" kind="cover" project={project.data}
      assets={assets.data ?? []} onPreview={setPreview} onChange={() => { assets.refresh(); project.refresh(); }} />}
    {preview && <Preview asset={preview} onClose={() => setPreview(undefined)} />}
  </>;
}
