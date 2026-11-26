import { Calculator, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, useAction, useResource } from "../api";
import { Button, ErrorLine, Field, IconButton, Modal } from "../ui";
import type { CostDraft, CostPlan, CostResult, Materials, Part, Plan } from "./PlanTypes";
import { type PriceList, type Unit, units } from "./Prices";

const partAmounts = [
  ["per_product", "每台用量（件）"], ["length", "部件长（mm）"], ["width", "部件宽（mm）"],
  ["height", "部件高（mm）"], ["thickness", "厚度（mm）"], ["weight_kg", "实测重量（kg）"],
  ["estimated_weight_kg", "参考重量（kg）"], ["density", "密度（g/cm³）"], ["unit_price", "实际采购单价（元）"],
  ["ai_price_kg", "AI 参考价（元/kg）"], ["loss_percent", "损耗（%）"], ["process_price", "加工费（元/件）"],
  ["finish_price", "表面处理费（元/件）"],
] as const;
const amounts = [
  ["quantity", "生产数量（台）"], ["length", "整机长（mm）"], ["width", "整机宽（mm）"], ["height", "整机高（mm）"],
  ["tooling", "一次性模具费（元）"], ["assembly", "每台装配费（元）"], ["hardware", "每台标准件费（元）"],
  ["electronics", "每台电子器件费（元）"], ["target", "目标单台成本（元）"],
  ["tax_rate", "换算税率（%）"], ["margin", "估算浮动（%）"],
] as const;
const requiredAmounts = new Set(["quantity", "tooling", "assembly", "hardware", "margin", "electronics"]);

function blankPart(): Part {
  return { name: "", material: "", grade: "", process: "", per_product: "1", length: null, width: null,
    height: null, thickness: null, weight_kg: null, estimated_weight_kg: null, density: null, price_id: null,
    unit_price: null, unit: "kg", ai_price_kg: null, loss_percent: null, process_price: null, finish_price: null };
}

function newDraft(plan?: Plan<Materials>): CostDraft {
  return {
    name: "成本方案", material_plan_id: plan?.id ?? null,
    parts: plan ? plan.data.components.map((part) => ({
      ...blankPart(), name: part.name, material: part.material, grade: part.grade, process: part.process.slice(0, 120),
      estimated_weight_kg: part.estimated_weight_kg, ai_price_kg: part.ai_price_kg,
    })) : [blankPart()],
    quantity: "1000", length: null, width: null, height: null, tooling: "0", assembly: "0", hardware: "0",
    electronics: "0", include_electronics: false, target: null, tax_included: false, tax_rate: null, margin: "15", notes: "",
  };
}

export function CostEditor({ version, plan, material, onClose, onSave }: {
  version: string; plan?: CostPlan; material?: Plan<Materials>; onClose: () => void; onSave: (plan: CostPlan) => void;
}) {
  const action = useAction();
  const [draft, setDraft] = useState<CostDraft>(() => plan?.data.inputs ?? newDraft(material));
  const [result, setResult] = useState<CostResult | undefined>(plan?.data.result);
  const [stale, setStale] = useState(false);
  const path = `/versions/${version}/costs`;
  function update<K extends keyof CostDraft>(key: K, value: CostDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value })); setStale(true);
  }
  function partUpdate(index: number, patch: Partial<Part>) {
    update("parts", draft.parts.map((part, current) => current === index ? { ...part, ...patch } : part));
  }
  function submit(mode: "calculate" | "save" | "copy") {
    void action.run(async () => {
      if (mode === "calculate") {
        setResult(await api<CostResult>(path + "/calculate", "POST", draft)); setStale(false);
      } else {
        const editing = !!plan && mode === "save";
        onSave(await api<CostPlan>(editing ? `${path}/${plan!.id}` : path, editing ? "PUT" : "POST", draft));
      }
    });
  }
  return <Modal wide title={plan ? "编辑并重新计算" : "新建成本方案"} onClose={onClose}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const button = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null;
      submit(button?.value === "copy" ? "copy" : button?.value === "save" ? "save" : "calculate");
    }}>
      <Field label="方案名称"><input value={draft.name} maxLength={120} required onChange={(event) => update("name", event.target.value)} /></Field>
      {material && <div className="notice">材料方案 · {material.name}。导入的参考重量与估价可逐项调整。</div>}
      <div className="form-grid three-fields">{amounts.map(([key, label]) => <Field key={key} label={label}>
        <input type="number" min={key === "quantity" ? 1 : 0} step={key === "quantity" ? 1 : "any"}
          max={key === "tax_rate" || key === "margin" ? 100 : undefined}
          required={requiredAmounts.has(key)} value={draft[key] ?? ""}
          onChange={(event) => update(key, event.target.value || (requiredAmounts.has(key) ? "" : null))} />
      </Field>)}</div>
      <div className="actions">
        <label className="check-row"><input type="checkbox" checked={draft.tax_included}
          onChange={(event) => update("tax_included", event.target.checked)} />结果含税</label>
        <label className="check-row"><input type="checkbox" checked={draft.include_electronics}
          onChange={(event) => update("include_electronics", event.target.checked)} />包含电子器件</label>
      </div>
      <div className="split-row"><h3>部件明细</h3><Button disabled={draft.parts.length >= 50}
        onClick={() => update("parts", [...draft.parts, blankPart()])}><Plus size={16} />新增部件</Button></div>
      {draft.parts.map((item, index) => <PartEditor key={index} item={item} index={index}
        change={(patch) => partUpdate(index, patch)}
        remove={draft.parts.length > 1 ? () => update("parts", draft.parts.filter((_, current) => current !== index)) : undefined} />)}
      <Field label="估算依据与其他费用" hint="自填金额采用上方税费口径，加工与表面处理可填 0 表示明确无费用。">
        <textarea rows={3} value={draft.notes} maxLength={3000} onChange={(event) => update("notes", event.target.value)} />
      </Field>
      <ErrorLine error={action.error} />
      <div className="actions">
        <Button type="submit" value="calculate" busy={action.busy}><Calculator size={16} />计算预览</Button>
        <Button type="submit" value="save" variant="primary" disabled={action.busy}>计算并保存</Button>
        {plan && <Button type="submit" value="copy" disabled={action.busy}>另存为方案</Button>}
      </div>
      {result && <><div className="notice">{stale ? "输入已变化，以下为上一次计算结果。" : "当前计算预览"}</div><CostBreakdown result={result} /></>}
    </form>
  </Modal>;
}

function PartEditor({ item, index, change, remove }: { item: Part; index: number; change: (patch: Partial<Part>) => void; remove?: () => void }) {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const prices = useResource<PriceList>(searching ? `/material-prices?limit=80&q=${encodeURIComponent(query || item.material)}` : null);
  return <section className="plan-part form-stack">
    <div className="split-row"><h3>{item.name || `部件 ${index + 1}`}</h3>
      {remove && <IconButton title={`移除部件 ${index + 1}`} onClick={remove}><Trash2 size={16} /></IconButton>}</div>
    <div className="form-grid three-fields">
      {([["name", "部件名称", 120], ["material", "材料名称", 100], ["grade", "牌号", 80], ["process", "加工工艺", 120]] as const)
        .map(([key, label, max]) => <Field key={key} label={label}><input value={item[key]} maxLength={max}
          required={key === "name" || key === "material"} onChange={(event) => change({ [key]: event.target.value })} /></Field>)}
      {partAmounts.map(([key, label]) => <Field key={key} label={label}><input type="number" value={item[key] ?? ""}
        min={key === "per_product" ? 1 : 0} max={key === "loss_percent" ? 90 : undefined}
        step={key === "per_product" ? 1 : "any"} required={key === "per_product"}
        onChange={(event) => change({ [key]: event.target.value || (key === "per_product" ? "" : null) })} /></Field>)}
      <Field label="采购价计价单位"><select value={item.unit} onChange={(event) => change({ unit: event.target.value as Unit })}>
        {Object.entries(units).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
    </div>
    <div className="actions">
      <Button onClick={() => setSearching(!searching)}>{searching ? "收起报价选择" : "选择价格库报价"}</Button>
      {item.price_id && <Button variant="ghost" onClick={() => change({ price_id: null })}>取消指定报价</Button>}
      <small className="subtle">{item.price_id ? "已指定报价" : "按材料及牌号自动匹配近期报价"}</small>
    </div>
    {searching && <div className="form-grid">
      <Field label="搜索价格库"><input value={query} maxLength={120} placeholder={item.material} onChange={(event) => setQuery(event.target.value)} /></Field>
      <Field label="报价记录"><select value={item.price_id ?? ""} onChange={(event) => change({ price_id: event.target.value || null })}>
        <option value="">自动匹配</option>
        {item.price_id && !prices.data?.items.some((itemPrice) => itemPrice.id === item.price_id) && <option value={item.price_id}>已指定报价</option>}
        {prices.data?.items.map((price) => <option key={price.id} value={price.id}>
          {price.name} {price.grade} · {price.supplier || price.source} · ¥{price.unit_price}/{units[price.unit]}
        </option>)}</select></Field>
      <ErrorLine error={prices.error} />
    </div>}
  </section>;
}

export function CostBreakdown({ result }: { result: CostResult }) {
  const shown = [["单台原材料", result.unit_material], ["单台制造", result.unit_manufacturing], ["批量总成本", result.batch_total],
    ["一次性模具", result.tooling], ["单台区间", result.range.join(" – ")]];
  return <div className="form-stack">
    <div className="notice">{result.quantity} 台 · 人民币 · {result.tax_included ? "含税" : "未税"} · {result.include_electronics ? "包含电子器件" : "电子器件未计入"}</div>
    {result.partial && <div className="notice warning">部分费用待确认。小计、总额和区间均基于已录入的项目。</div>}
    <div className="cost-metrics">{shown.map(([label, number]) => <div key={label}><small>{label}</small><strong>¥{number}</strong></div>)}</div>
    {result.target_gap !== null && <p className="subtle compact">单台成本与目标差额 ¥{result.target_gap}</p>}
    <div className="table-scroll"><table>
      <thead><tr><th>预估 BOM</th><th>采购量 / 台</th><th>材料费</th><th>加工费</th><th>表面处理</th><th>小计 / 台</th></tr></thead>
      <tbody>{result.bom.map((line, index) => <tr key={index}>
        <td><strong>{line.name} · {line.material}</strong><small>{line.grade} {line.per_product} 件 / 台 · {line.source}</small>
          {line.missing.map((issue, i) => <small className="cost-missing" key={i}>{issue}</small>)}</td>
        <td>{line.purchase ?? "待确认"} {units[line.unit]}<small>损耗 {line.loss_percent}%</small></td>
        <td>{line.raw ?? "待确认"}<small>{line.unit_price !== null && `¥${line.unit_price} / ${units[line.unit]}`}</small></td>
        <td>{line.processing ?? "待确认"}<small>{line.process_source}</small></td><td>{line.surface ?? "待确认"}</td><td>¥{line.total}</td>
      </tr>)}</tbody>
    </table></div>
    <details><summary>价格来源、计算依据与降本建议</summary>
      <div className="form-stack top-gap">
        <p className="compact">每台费用 · 加工 ¥{result.unit_processing} · 表面 ¥{result.unit_surface} · 装配 ¥{result.unit_assembly} · 标准件 ¥{result.unit_hardware} · 电子件 ¥{result.unit_electronics} · 模具分摊 ¥{result.unit_tooling}</p>
        {result.bom.map((line, index) => <div key={index} className="notice"><div><strong>{line.name} · {line.source}</strong>
          {line.library && <p>{[line.library.supplier, line.library.spec, line.library.source, line.library.price_date].filter(Boolean).join(" · ")}</p>}
          {line.weight_kg && <p>单件重量 {line.weight_kg} kg</p>}
          {line.assumptions.map((assumption) => <p key={assumption}>{assumption}</p>)}
        </div></div>)}
        <ul className="compact">{[...result.basis, ...result.suggestions].map((item) => <li key={item}>{item}</li>)}</ul>
      </div>
    </details>
  </div>;
}
