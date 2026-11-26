import { GitBranch, ImageIcon, ListTree, ScanLine, SlidersHorizontal, Sparkles, WandSparkles } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { api, assetUrl, useAction, useResource, useSubmission } from "../api";
import type { Asset, Catalog, Job, Project, VersionDetail } from "../types";
import { Button, Empty, ErrorLine, Field, Loading, Modal } from "../ui";
import { JobItem } from "./Jobs";
import { VersionLinks, VersionParams, versionNumber } from "./Versions";

interface PromptPreview { prompt: string; warnings: string[]; mock: boolean }

interface DesignProps {
  project: Project; assets: Asset[]; onPreview: (asset: Asset) => void;
  sources: ReactNode; parentId?: string; clearParent: () => void;
}
export function DesignPanel({ parentId, ...props }: DesignProps) {
  const catalog = useResource<Catalog>("/design/catalog");
  const chosen = useResource<VersionDetail>(parentId ? `/versions/${parentId}` : null);
  if (!catalog.data || chosen.loading) return <><ErrorLine error={catalog.error} />{(catalog.loading || chosen.loading) && <Loading />}</>;
  const parent = chosen.data?.project_id === props.project.id && chosen.data.asset ? chosen.data : undefined;
  return <>
    {parentId && !parent && <div className="actions"><ErrorLine error={chosen.error ?? "无法使用此版本作为迭代输入"} />
      <Button onClick={props.clearParent}>取消迭代输入</Button></div>}
    <DesignForm key={parent?.id ?? "initial"} {...props} catalog={catalog.data} parent={parent} />
  </>;
}

function DesignForm({ project, assets, catalog, onPreview, sources, parent, clearParent }: Omit<DesignProps, "parentId"> & {
  catalog: Catalog; parent?: VersionDetail;
}) {
  const route = `/projects/${project.id}`;
  const jobs = useResource<Job[]>(`${route}/jobs?limit=15`, 1600);
  const action = useAction();
  const submit = useSubmission();
  const [main, setMain] = useState(parent?.configuration.templates.main.id ?? "");
  const [level, setLevel] = useState(parent?.configuration.templates.level.id ?? "");
  const [auxiliary, setAuxiliary] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [raw, setRaw] = useState("");
  const [optimized, setOptimized] = useState("");
  const [final, setFinal] = useState("");
  const [constraints, setConstraints] = useState(parent?.configuration.constraints ?? "");
  const [modelId, setModelId] = useState("");
  const [ratio, setRatio] = useState("");
  const [size, setSize] = useState("");
  const [count, setCount] = useState(1);
  const [background, setBackground] = useState("studio");
  const [view, setView] = useState("three_quarter");
  const [consent, setConsent] = useState(false);
  const [preview, setPreview] = useState<{ data: PromptPreview; send: boolean; body: object }>();
  const [optimization, setOptimization] = useState<Job>();
  const [parameters, setParameters] = useState<string>();
  const anchor = useRef<HTMLDivElement>(null);
  const modelPicker = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    if (parent?.id) anchor.current?.scrollIntoView({ block: "start" });
  }, [parent?.id]);

  const directions = catalog.templates.filter((row) => row.kind === "direction");
  const levels = catalog.templates.filter((row) => row.kind === "level").sort((a, b) => a.slug.localeCompare(b.slug));
  const chosenMain = directions.find((row) => row.id === main) ?? directions[0];
  const chosenLevel = levels.find((row) => row.id === level) ?? levels.find((row) => row.slug === "l3");
  const task = parent ? "edit" : "generate";
  const models = catalog.models.filter((row) => row.tasks?.includes(task));
  const active = models.find((row) => row.id === (modelId || catalog.defaults[task])) ?? models[0];
  const ratios = [...new Set(active?.sizes.map((item) => item.ratio) ?? [])];
  const selectedRatio = ratios.includes(ratio) ? ratio : ratios[0];
  const sizes = active?.sizes.filter((item) => item.ratio === selectedRatio) ?? [];
  const spec = sizes.find((item) => item.value === size) ?? sizes[0];
  const candidates = [...new Map([
    ...(parent?.originals ?? []), ...(parent?.references ?? []),
    ...assets.filter((asset) => asset.kind === "original" || asset.kind === "reference"),
  ].map((asset) => [asset.id, asset])).values()];
  const originals = candidates.filter((row) => row.kind === "original" && !excluded.includes(row.id)).map((row) => row.id);
  const references = candidates.filter((row) => row.kind === "reference" && !excluded.includes(row.id)).map((row) => row.id);
  const external = active?.protocol !== "mock" || [catalog.defaults.optimize, catalog.defaults.inspect]
    .some((id) => catalog.models.some((row) => row.id === id && row.protocol !== "mock"));
  const hasInputs = !!originals.length && !!chosenMain && !!chosenLevel && !!spec
    && originals.length + references.length + Number(!!parent) <= (active?.max_inputs ?? 0);

  const body = {
    originals, references, main: chosenMain?.id, auxiliary: auxiliary.filter((id) => id !== chosenMain?.id),
    level: chosenLevel?.id, raw, optimized, final, constraints, model_id: active?.id, parent_id: parent?.id,
    output: { count: Math.min(count, active?.max_count ?? 1), ratio: selectedRatio, size: spec?.value, background, view },
  };

  async function queueGenerate(data: object, confirmed: boolean) {
    await submit<Job>(`${route}/generate`, { ...data, ack_conflicts: confirmed, ack_external: consent });
    setPreview(undefined); jobs.refresh();
  }
  function promptPreview(send: boolean) {
    void action.run(async () => {
      const data = await api<PromptPreview>(`${route}/preview`, "POST", body);
      if (send && !data.warnings.length) await queueGenerate(body, false);
      else setPreview({ data, send, body });
    });
  }
  const disabled = project.archived || action.busy;

  return <>
    <div className="studio-grid">
      <div className="studio-inputs">
        <div id="design-config" ref={anchor} />
        {parent?.asset && <section className="panel form-stack">
          <div className="split-row"><h2><GitBranch size={17} />当前迭代图片 · {versionNumber(parent.number)}</h2>
            <Button variant="ghost" onClick={clearParent}>取消迭代</Button></div>
          <button type="button" className="compare-image iteration-image" onClick={() => onPreview(parent.asset!)}>
            <img src={assetUrl(parent.asset.id)} alt={`${versionNumber(parent.number)} 迭代输入`} /></button>
          <p className="subtle compact">以当前版本的造型为基础，使用原图校对功能区域。</p>
        </section>}
        {sources}
        <section className="panel form-stack">
          <h2><SlidersHorizontal size={17} />设计方向</h2>
          <Field label="主执行方向" hint={chosenMain?.summary}>
            <select value={chosenMain?.id ?? ""} onChange={(event) => setMain(event.target.value)} disabled={disabled}>
              {directions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </Field>
          <div><div className="field-label">辅助方向 <span className="subtle">最多 5 个</span></div>
            <div className="chips">{directions.filter((row) => row.id !== chosenMain?.id).map((item) =>
              <button type="button" key={item.id} title={item.summary} aria-pressed={auxiliary.includes(item.id)}
                className={auxiliary.includes(item.id) ? "active" : ""}
                disabled={disabled || auxiliary.length >= 5 && !auxiliary.includes(item.id)}
                onClick={() => setAuxiliary(auxiliary.includes(item.id) ? auxiliary.filter((id) => id !== item.id) : [...auxiliary, item.id])}>
                {item.name}
              </button>)}
            </div>
          </div>
          <div><div className="field-label">重构幅度</div>
            <div className="level-grid">{levels.map((item) => <button key={item.id} type="button" disabled={disabled}
              title={item.name} className={chosenLevel?.id === item.id ? "active" : ""}
              aria-label={`${item.slug.toUpperCase()} ${item.name}`} aria-pressed={chosenLevel?.id === item.id}
              onClick={() => setLevel(item.id)}>{item.slug.toUpperCase()}</button>)}</div>
            {chosenLevel && <p className="subtle level-help"><strong>{chosenLevel.name}</strong> · {chosenLevel.summary}</p>}
          </div>
        </section>
        <section className="panel form-stack">
          <h2><WandSparkles size={17} />设计需求</h2>
          <Field label="原始需求"><textarea rows={4} maxLength={3500} value={raw} onChange={(event) => setRaw(event.target.value)}
            placeholder="描述希望修改的造型、材质、颜色、功能或成本约束。" disabled={disabled} /></Field>
          <Field label="必须保留"><textarea rows={2} maxLength={1800} value={constraints} onChange={(event) => setConstraints(event.target.value)}
            placeholder="例如 保留侧面的电源接口和底座装配尺寸" disabled={disabled} /></Field>
          {(optimized || final) && <Field label="最终需求" hint="可直接编辑。原文和优化结果均会随版本保留。">
            <textarea rows={6} maxLength={6000} value={final} onChange={(event) => setFinal(event.target.value)} disabled={disabled} />
          </Field>}
          <div className="actions">
            <Button disabled={disabled || !raw.trim()} onClick={() => void action.run(async () => {
              const job = await submit<Job>(`${route}/optimize`, {
                raw, constraints, main: chosenMain?.id, level: chosenLevel?.id, ack_external: consent,
              });
              jobs.refresh(); setOptimization(job);
            })}><Sparkles size={16} />{optimized ? "重新优化" : "AI 优化"}</Button>
            {(optimized || final) && <Button variant="ghost" onClick={() => { setOptimized(""); setFinal(""); }} disabled={disabled}>恢复原始需求</Button>}
          </div>
        </section>
        <section className="panel form-stack">
          <div className="split-row"><h2>输出设置</h2>{active?.protocol === "mock" && <span className="badge">Mock 模式</span>}</div>
          <Field label="图片模型"><select ref={modelPicker} value={active?.id ?? ""} onChange={(event) => { setModelId(event.target.value); setRatio(""); setSize(""); }}
            disabled={disabled}>{models.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></Field>
          <div className="form-grid">
            <Field label="图片比例"><select value={selectedRatio ?? ""} onChange={(event) => { setRatio(event.target.value); setSize(""); }} disabled={disabled}>
              {ratios.map((item) => <option key={item}>{item}</option>)}
            </select></Field>
            <Field label="输出分辨率"><select value={spec?.value ?? ""} onChange={(event) => setSize(event.target.value)} disabled={disabled}>
              {sizes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select></Field>
            <Field label="生成数量"><select value={body.output.count} onChange={(event) => setCount(Number(event.target.value))} disabled={disabled}>
              {Array.from({ length: active?.max_count ?? 1 }, (_, index) => <option key={index} value={index + 1}>{index + 1} 张</option>)}
            </select></Field>
            <Field label="背景"><select value={background} onChange={(event) => setBackground(event.target.value)} disabled={disabled}>
              <option value="studio">中性摄影棚</option><option value="white">纯白</option><option value="dark">深色</option><option value="context">使用场景</option>
            </select></Field>
            <Field label="产品视角"><select value={view} onChange={(event) => setView(event.target.value)} disabled={disabled}>
              <option value="three_quarter">三分之四视角</option><option value="front">正视角</option><option value="side">侧视角</option><option value="top">俯视角</option>
            </select></Field>
          </div>
          {!!candidates.length && <details className="input-selection">
            <summary>选入图片 · {originals.length} 张原图、{references.length} 张参考图</summary>
            <div className="form-stack">
              {candidates.map((asset) => <label key={asset.id} className="check-row">
                <input type="checkbox" checked={!excluded.includes(asset.id)} disabled={disabled}
                  onChange={(event) => setExcluded(event.target.checked ? excluded.filter((id) => id !== asset.id) : [...excluded, asset.id])} />
                <span>{asset.kind === "original" ? "原图" : "参考"} · {asset.filename}</span>
              </label>)}
              <Button disabled={disabled || !originals.length} onClick={() => void action.run(async () => {
                await submit<Job>(`${route}/inspect`, { originals, ack_external: consent }); jobs.refresh();
              })}><ScanLine size={16} />分析选入的原图</Button>
            </div>
          </details>}
          {active?.protocol === "mock" && <p className="subtle compact">Mock 使用本地素材模拟配色和规格，供流程验证。</p>}
          {external && <label className="check-row notice warning"><input type="checkbox" checked={consent}
            onChange={(event) => setConsent(event.target.checked)} />同意向外部模型发送所选输入。调用可能产生费用。</label>}
          {!hasInputs && <p className="subtle compact">请选择原图、有效模板和图片模型，并检查输入张数上限。</p>}
          <ErrorLine error={action.error} />
          <div className="actions">
            <Button variant="primary" busy={action.busy && !preview} disabled={disabled || !hasInputs} onClick={() => promptPreview(true)}><Sparkles size={18} />{parent ? "生成迭代版本" : "生成设计"}</Button>
            <Button disabled={disabled || !hasInputs} onClick={() => promptPreview(false)}>预览提示词</Button>
          </div>
        </section>
      </div>
      <div className="studio-output">
        <section className="panel output-panel">
          <div className="section-heading"><div><h2>生成任务与成果</h2><p>查看最近任务与新生成的设计版本。</p></div></div>
          <ErrorLine error={jobs.error} />
          {jobs.loading && <Loading />}
          {!jobs.loading && !jobs.data?.length && <Empty icon={<ImageIcon size={25} />} title="等待首个设计成果" description="提交设计后在这里查看队列状态、预览和下载。" />}
          <div className="form-stack">{jobs.data?.map((job) => {
            const originalModel = catalog.models.find((row) => row.id === job.model_id);
            const retryBlocked = job.status === "failed" && (job.kind === "generate" || job.kind === "edit")
              && (!originalModel?.tasks?.includes(job.kind) || Boolean(job.model_code && originalModel.model_code !== job.model_code));
            return <JobItem key={job.id} job={job} onPreview={onPreview} refresh={jobs.refresh} canRetry={!retryBlocked}
              assetActions={(index) => {
                const id = job.result?.version_ids?.[index];
                return id ? <><VersionLinks id={id} project={project.id} />
                  <Button variant="ghost" onClick={() => setParameters(id)}><ListTree size={15} />参数</Button></> : null;
              }}>
              {retryBlocked && <div className="form-stack">
                <p className="subtle compact">原任务的图片模型当前不可用。请选择有效模型创建新任务。</p>
                {job.kind === task && <div className="actions">
                  <Button variant="ghost" disabled={disabled} onClick={() => modelPicker.current?.focus()}>前往生成设置</Button>
                </div>}
              </div>}
              {job.result?.optimized && <Button onClick={() => setOptimization(job)}>查看优化结果</Button>}
            </JobItem>;
          })}</div>
        </section>
      </div>
    </div>
    {preview && <Modal title="最终模型提示词" onClose={() => setPreview(undefined)} wide>
      <div className="form-stack">
        {preview.data.warnings.map((warning) => <div key={warning} className="notice warning">{warning}</div>)}
        <pre className="text-preview">{preview.data.prompt}</pre>
        <ErrorLine error={action.error} />
        {preview.send && <Button variant="primary" busy={action.busy}
          onClick={() => void action.run(() => queueGenerate(preview.body, true))}>确认约束并生成</Button>}
      </div>
    </Modal>}
    {optimization && <OptimizeResult initial={optimization} onClose={() => setOptimization(undefined)}
      onApply={(value) => { setOptimized(value); setFinal(value); setOptimization(undefined); }} />}
    {parameters && <VersionParams id={parameters} onClose={() => setParameters(undefined)} />}
  </>;
}

function OptimizeResult({ initial, onClose, onApply }: { initial: Job; onClose: () => void; onApply: (text: string) => void }) {
  const current = useResource<Job>(`/jobs/${initial.id}`, 1300);
  const job = current.data ?? initial;
  return <Modal title="AI 提示词优化" onClose={onClose}>
    <JobItem job={job} refresh={current.refresh} />
    {job.result?.optimized && <div className="form-stack modal-meta">
      {job.result.conflicts?.map((warning) => <div key={warning} className="notice warning">{warning}</div>)}
      <pre className="text-preview">{job.result.optimized}</pre>
      <Button variant="primary" onClick={() => onApply(job.result!.optimized!)}>采用并编辑</Button>
    </div>}
    <ErrorLine error={current.error} />
  </Modal>;
}
