import { Calculator, FlaskConical, Layers3, PencilLine, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, assetUrl, dateTime, useAction, useResource, useSubmission } from "../api";
import type { Asset, Catalog, Job, VersionDetail } from "../types";
import { Button, Empty, ErrorLine, Field, Heading, IconButton, Loading, Modal, Preview } from "../ui";
import { CostBreakdown, CostEditor } from "./CostEditor";
import { JobItem } from "./Jobs";
import type { AnalysisData, Component, CostPlan, Materials, Plan } from "./PlanTypes";
import { ProjectSelect } from "./Projects";
import { versionNumber } from "./Versions";

type AnalysisKind = "materials" | "manufacturing" | "cost_advice";
const materialFields = [
  ["name", "部件名称"], ["function", "部件功能"], ["material", "推荐材料"], ["grade", "材料牌号"],
  ["spec", "厚度或规格"], ["process", "制造工艺"], ["finish", "表面处理"], ["reason", "选型原因"],
  ["quantity_estimate", "预估用量"], ["risk", "制造风险"], ["savings", "降本建议"], ["assumptions", "假设与不确定因素"],
] as const;
function blankComponent(): Component {
  return { name: "", function: "", material: "", grade: "", spec: "", process: "", finish: "", reason: "",
    alternatives: [], quantity_estimate: "", estimated_weight_kg: null, ai_price_kg: null, risk: "", savings: "", assumptions: "" };
}

export function AnalysisPage() {
  const [params, setParams] = useSearchParams();
  const project = params.get("project") ?? "";
  const version = params.get("version") ?? "";
  const tab = params.get("tab") === "cost" ? "cost" : "materials";
  const items = useResource<{ id: string; label: string; kind: string }[]>(project ? `/projects/${project}/comparison-options` : null);
  const detail = useResource<VersionDetail>(version ? `/versions/${version}` : null);
  return <>
    <Heading title="材料与成本" description="按设计版本维护选型建议、制造依据与人民币成本方案。" />
    <div className="toolbar">
      <ProjectSelect selected={project} onSelect={(id) => setParams(id ? { project: id, tab } : { tab })} />
      <Field label="设计版本"><select value={version} disabled={!project} onChange={(event) => setParams({ project, tab, version: event.target.value })}>
        <option value="">选择已生成版本</option>
        {items.data?.filter((row) => row.kind === "version").map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
      </select></Field>
    </div>
    <ErrorLine error={items.error || detail.error} />{detail.loading && <Loading />}
    {detail.data?.asset && detail.data.project_id === project ? <VersionAnalysis key={version} version={detail.data} tab={tab}
      changeTab={(next) => setParams({ project, version, tab: next })} /> : !detail.loading && <div className="panel">
      <Empty icon={<Layers3 size={24} />} title="选择设计版本开始分析" /></div>}
  </>;
}

function VersionAnalysis({ version, tab, changeTab }: { version: VersionDetail; tab: string; changeTab: (tab: string) => void }) {
  const path = `/versions/${version.id}`;
  const data = useResource<AnalysisData>(path + "/analysis", 1800);
  const catalog = useResource<Catalog>("/design/catalog");
  const submit = useSubmission();
  const action = useAction();
  const [consent, setConsent] = useState(false);
  const [notes, setNotes] = useState("");
  const [preview, setPreview] = useState<Asset>();
  const [materialSource, setMaterialSource] = useState("");
  const [materials, setMaterials] = useState<{ row?: Plan<Materials>; draft?: Materials; job?: string }>();
  const [cost, setCost] = useState<{ row?: CostPlan; material?: Plan<Materials> }>();
  const [openCost, setOpenCost] = useState("");
  const kinds: AnalysisKind[] = tab === "cost" ? ["cost_advice"] : ["materials", "manufacturing"];
  const needsConsent = kinds.some((kind) => catalog.data?.models.some((row) => row.id === catalog.data?.defaults[kind] && row.protocol !== "mock"));
  function start(kind: AnalysisKind) {
    void action.run(async () => {
      await submit<Job>(path + "/analysis", { kind, notes, ack_external: consent }); data.refresh();
    });
  }
  return <>
    <section className="panel analysis-banner">
      <button className="compare-image" type="button" onClick={() => setPreview(version.asset!)}>
        <img src={assetUrl(version.asset!.id)} alt="分析所用的设计成果" />
      </button>
      <div className="form-stack"><div><h2>{version.project_name} · {versionNumber(version.number)}</h2>
        <p className="subtle compact">二维概念图。内部结构、尺寸、重量和真实报价以测量或供应商数据为准。</p></div>
        <div className="actions"><Link className="btn btn-secondary" to={`/projects/${version.project_id}`}>打开项目</Link>
          {version.mock && <span className="badge">Mock 成果</span>}</div>
      </div>
    </section>
    <div className="tabs">
      <button className={tab === "materials" ? "active" : ""} onClick={() => changeTab("materials")}>材料选型</button>
      <button className={tab === "cost" ? "active" : ""} onClick={() => changeTab("cost")}>成本评估</button>
    </div>
    <section className="panel form-stack">
      <div className="split-row"><h2><FlaskConical size={17} />{tab === "cost" ? "成本辅助分析" : "AI 材料与工艺分析"}</h2>
        {tab === "materials" && <Button onClick={() => setMaterials({})}><Plus size={17} />手工创建方案</Button>}</div>
      <Field label="分析补充条件"><textarea rows={2} maxLength={2000} value={notes} onChange={(event) => setNotes(event.target.value)}
        placeholder="例如 使用环境、制造数量、抗冲击要求或成本约束" /></Field>
      {needsConsent && <label className="check-row notice warning"><input type="checkbox" checked={consent}
        onChange={(event) => setConsent(event.target.checked)} />同意向外部模型发送此版本图片与补充条件，调用可能产生费用。</label>}
      <ErrorLine error={action.error || data.error || catalog.error} />
      <div className="actions">
        {kinds.map((kind) => <Button key={kind} variant={kind === "manufacturing" ? "secondary" : "primary"} busy={action.busy}
          disabled={!catalog.data || !!needsConsent && !consent} onClick={() => start(kind)}>
          <Sparkles size={16} />{kind === "materials" ? "运行材料分析" : kind === "manufacturing" ? "分析制造工艺" : "分析降本机会"}
        </Button>)}
      </div>
      {data.loading && <Loading />}
      {data.data?.jobs.filter((job) => kinds.includes(job.kind as AnalysisKind)).map((job) => <JobItem key={job.id} job={job} refresh={data.refresh}>
        {job.kind === "materials" && job.result?.components && <>
          <p className="subtle compact">{job.result.components.map((item) => item.name + " · " + item.material).join("、")}</p>
          <Button onClick={() => setMaterials({ draft: job.result as Materials, job: job.id })}>采用并编辑材料建议</Button>
        </>}
      </JobItem>)}
    </section>
    {tab === "materials" ? <section className="panel form-stack">
      <h2><Layers3 size={17} />已保存材料方案</h2>
      {data.data?.materials.length === 0 && <Empty title="还没有材料方案" />}
      {data.data?.materials.map((row) => <article key={row.id} className="plan-part form-stack">
        <div className="split-row"><div><h3>{row.name}</h3><p className="subtle compact">{dateTime(row.updated_at)}</p></div>
          <div className="actions"><Button onClick={() => setMaterials({ row })}><PencilLine size={16} />编辑</Button>
            <Button onClick={() => setCost({ material: row })}><Calculator size={16} />按此方案估算</Button></div></div>
        <p className="compact">{row.data.summary}</p>
        <div className="table-scroll"><table><thead><tr><th>部件</th><th>材料 / 牌号</th><th>规格</th><th>工艺及表面</th></tr></thead>
          <tbody>{row.data.components.map((component, index) => <tr key={index}>
            <td>{component.name}<small>{component.function}</small></td><td>{component.material}<small>{component.grade}</small></td>
            <td>{component.spec || "待确认"}</td><td>{component.process || "待确认"}<small>{component.finish}</small></td>
          </tr>)}</tbody></table></div>
        {!!row.data.uncertainties.length && <div className="notice warning">{row.data.uncertainties.join("；")}</div>}
      </article>)}
    </section> : <section className="panel form-stack">
      <div className="section-heading"><div><h2><Calculator size={17} />BOM 与成本方案</h2><p>按当前资料计算，价格来源和计算明细随方案保存。</p></div>
        <Button variant="primary" onClick={() => setCost({ material: data.data?.materials.find((row) => row.id === materialSource) })}><Plus size={16} />新建成本方案</Button></div>
      {!!data.data?.materials.length && <Field label="从材料方案读取部件"><select value={materialSource} onChange={(event) => setMaterialSource(event.target.value)}>
        <option value="">手工录入 BOM</option>{data.data.materials.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select></Field>}
      {data.data?.costs.length === 0 && <Empty title="还没有成本方案" />}
      {data.data?.costs.map((row) => <article className="plan-part form-stack" key={row.id}>
        <div className="split-row"><div><h3>{row.name}</h3><p className="subtle compact">{dateTime(row.updated_at)} · {row.data.result.quantity} 台 · ¥{row.data.result.unit_manufacturing} / 台</p></div>
          <div className="actions"><Button onClick={() => setOpenCost(openCost === row.id ? "" : row.id)}>{openCost === row.id ? "收起明细" : "查看明细"}</Button>
            <Button onClick={() => setCost({ row })}><PencilLine size={16} />编辑与重算</Button></div></div>
        {openCost === row.id && <CostBreakdown result={row.data.result} />}
      </article>)}
    </section>}
    {materials && <MaterialEditor version={version.id} {...materials} close={() => setMaterials(undefined)}
      saved={() => { setMaterials(undefined); data.refresh(); }} />}
    {cost && <CostEditor version={version.id} plan={cost.row} material={cost.material} onClose={() => setCost(undefined)}
      onSave={(saved) => { setCost(undefined); setOpenCost(saved.id); data.refresh(); changeTab("cost"); }} />}
    {preview && <Preview asset={preview} onClose={() => setPreview(undefined)} />}
  </>;
}

function MaterialEditor({ version, row, draft, job, close, saved }: {
  version: string; row?: Plan<Materials>; draft?: Materials; job?: string; close: () => void; saved: () => void;
}) {
  const [name, setName] = useState(row?.name ?? "材料选型方案");
  const [data, setData] = useState<Materials>(row?.data ?? draft ?? { summary: "", components: [blankComponent()], uncertainties: [], cost_suggestions: [] });
  const action = useAction();
  function edit(index: number, patch: Partial<Component>) {
    setData((value) => ({ ...value, components: value.components.map((item, position) => index === position ? { ...item, ...patch } : item) }));
  }
  return <Modal wide title={row ? "编辑材料方案" : "新建材料方案"} onClose={close}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const copy = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "copy";
      const path = `/versions/${version}/materials`;
      void action.run(async () => {
        await api(row && !copy ? `${path}/${row.id}` : path, row && !copy ? "PUT" : "POST", {
          name, data, job_id: row?.job_id ?? job ?? null,
        }); saved();
      });
    }}>
      <div className="form-grid">
        <Field label="方案名称"><input value={name} maxLength={120} required onChange={(event) => setName(event.target.value)} /></Field>
        <Field label="方案概述"><input value={data.summary} maxLength={1200} onChange={(event) => setData({ ...data, summary: event.target.value })} /></Field>
      </div>
      <div className="split-row"><h3>部件选型</h3><Button disabled={data.components.length >= 30}
        onClick={() => setData({ ...data, components: [...data.components, blankComponent()] })}><Plus size={17} />添加部件</Button></div>
      {data.components.map((part, index) => <div className="plan-part form-stack" key={index}>
        <div className="split-row"><h3>{part.name || `部件 ${index + 1}`}</h3>
          {data.components.length > 1 && <IconButton title={`移除部件 ${index + 1}`} onClick={() =>
            setData({ ...data, components: data.components.filter((_, position) => position !== index) })}><Trash2 size={16} /></IconButton>}
        </div>
        <div className="form-grid three-fields">
          {materialFields.map(([key, label]) => <Field key={key} label={label}>
            <textarea rows={key === "name" || key === "material" ? 1 : 2} value={part[key]}
              maxLength={key === "name" ? 120 : key === "material" ? 100 : key === "grade" ? 80 : 1200}
              required={key === "name" || key === "material"} onChange={(event) => edit(index, { [key]: event.target.value })} />
          </Field>)}
          <Field label="替代材料" hint="每行一种"><textarea rows={2} value={part.alternatives.join("\n")}
            onChange={(event) => edit(index, { alternatives: event.target.value.split("\n") })} /></Field>
          <Field label="参考重量（kg）"><input type="number" min={0} step="any" value={part.estimated_weight_kg ?? ""}
            onChange={(event) => edit(index, { estimated_weight_kg: event.target.value || null })} /></Field>
          <Field label="AI 参考估价（元/kg）"><input type="number" min={0} step="any" value={part.ai_price_kg ?? ""}
            onChange={(event) => edit(index, { ai_price_kg: event.target.value || null })} /></Field>
        </div>
      </div>)}
      <div className="form-grid">
        <Field label="待确认事项" hint="每行一项"><textarea rows={3} value={data.uncertainties.join("\n")}
          onChange={(event) => setData({ ...data, uncertainties: event.target.value.split("\n") })} /></Field>
        <Field label="成本优化建议" hint="每行一项"><textarea rows={3} value={data.cost_suggestions.join("\n")}
          onChange={(event) => setData({ ...data, cost_suggestions: event.target.value.split("\n") })} /></Field>
      </div>
      <ErrorLine error={action.error} />
      <div className="actions dialog-actions"><Button onClick={close}>取消</Button>
        {row && <Button type="submit" value="copy" disabled={action.busy}>另存为方案</Button>}
        <Button type="submit" variant="primary" busy={action.busy}>保存材料方案</Button></div>
    </form>
  </Modal>;
}
