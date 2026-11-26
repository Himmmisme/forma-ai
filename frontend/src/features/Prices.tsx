import { Download, PencilLine, Plus, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, useAction, useResource } from "../api";
import { Button, Empty, ErrorLine, Field, IconButton, Loading, Modal } from "../ui";

export const units = { kg: "kg", piece: "件", m2: "m²", m: "m" };
export type Unit = keyof typeof units;
export interface Price {
  id: string; name: string; grade: string; spec: string; density: string | null; unit_price: string; unit: Unit;
  loss_rate: string; process: string; process_price: string | null; supplier: string; source: string;
  price_date: string; tax_included: boolean;
}
export interface PriceList { items: Price[]; more: boolean }

export function PricesPanel() {
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [editor, setEditor] = useState<{ item?: Price }>();
  const [notice, setNotice] = useState("");
  const upload = useRef<HTMLInputElement>(null);
  const action = useAction();
  const rows = useResource<PriceList>(`/material-prices?q=${encodeURIComponent(query)}&offset=${offset}`);
  return <section className="panel form-stack">
    <div className="section-heading"><div><h2>材料价格库</h2><p>维护实际报价、计价单位、损耗、加工参考价与来源。</p></div>
      <Button variant="primary" onClick={() => setEditor({})}><Plus size={16} />新增报价</Button></div>
    <div className="toolbar"><Field label="搜索报价"><input value={query} maxLength={120} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} placeholder="材料、牌号或供应商" /></Field>
      <div className="actions">
        <a className="btn btn-ghost" href="/api/admin/prices/export?template=true"><Download size={16} />Excel 模板</a>
        <a className="btn btn-secondary" href="/api/admin/prices/export"><Download size={16} />导出 Excel</a>
        <Button busy={action.busy} onClick={() => upload.current?.click()}><Upload size={16} />导入 Excel</Button>
        <input hidden type="file" accept=".xlsx" ref={upload} onChange={(event) => {
          const file = event.target.files?.[0]; event.target.value = "";
          if (!file) return;
          setNotice("");
          void action.run(async () => {
            const form = new FormData(); form.append("file", file);
            const result = await api<{ created: number; updated: number }>("/admin/prices/import", "POST", form);
            setNotice(`已导入 ${result.created} 条新报价，更新 ${result.updated} 条`); rows.refresh();
          });
        }} />
      </div>
    </div>
    {notice && <div className="notice success" role="status">{notice}</div>}
    <ErrorLine error={action.error || rows.error} />{rows.loading && <Loading />}
    {rows.data?.items.length === 0 && <Empty title="没有报价记录" />}
    {!!rows.data?.items.length && <div className="table-scroll"><table>
      <thead><tr><th>材料与规格</th><th>采购单价</th><th>加工工艺</th><th>损耗</th><th>来源 / 日期</th><th>操作</th></tr></thead>
      <tbody>{rows.data.items.map((item) => <tr key={item.id}>
        <td><strong>{item.name}</strong><small>{[item.grade, item.spec, item.density && `${item.density} g/cm³`].filter(Boolean).join(" · ")}</small></td>
        <td>¥{item.unit_price} / {units[item.unit]}<small>{item.tax_included ? "含税" : "未税"}</small></td>
        <td>{item.process || "—"}{item.process_price !== null && <small>¥{item.process_price} / 件</small>}</td>
        <td>{item.loss_rate}%</td><td>{item.supplier || item.source}<small>{item.price_date} · {item.source}</small></td>
        <td><IconButton title={`编辑 ${item.name}`} onClick={() => setEditor({ item })}><PencilLine size={17} /></IconButton></td>
      </tr>)}</tbody>
    </table></div>}
    {(offset > 0 || rows.data?.more) && <div className="actions pager"><Button disabled={!offset} onClick={() => setOffset(offset - 60)}>上一页</Button>
      <Button disabled={!rows.data?.more} onClick={() => setOffset(offset + 60)}>下一页</Button></div>}
    {editor && <PriceEditor item={editor.item} close={() => setEditor(undefined)} saved={() => { setEditor(undefined); rows.refresh(); }} />}
  </section>;
}

function PriceEditor({ item, close, saved }: { item?: Price; close: () => void; saved: () => void }) {
  const action = useAction();
  const words = [["name", "材料名称", 100], ["grade", "材料牌号", 80], ["spec", "规格", 120],
    ["process", "加工工艺", 120], ["supplier", "供应商", 120], ["source", "价格来源", 160]] as const;
  const numbers = [["density", "密度（g/cm³）"], ["unit_price", "采购单价（元）"],
    ["loss_rate", "损耗率（%）"], ["process_price", "加工参考价（元/件）"]] as const;
  return <Modal title={item ? "编辑材料报价" : "新增材料报价"} onClose={close} wide>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget));
      const payload = { ...values, density: values.density || null, process_price: values.process_price || null,
        loss_rate: values.loss_rate || "0", tax_included: values.tax_included === "on" };
      void action.run(async () => {
        await api(item ? `/admin/prices/${item.id}` : "/admin/prices", item ? "PUT" : "POST", payload);
        saved();
      });
    }}>
      <div className="form-grid">
        {words.map(([key, label, max]) => <Field label={label} key={key}><input name={key} maxLength={max}
          required={key === "name" || key === "source"} defaultValue={item?.[key]} /></Field>)}
        {numbers.map(([key, label]) => <Field label={label} key={key}><input name={key} type="number" step="any" min={0}
          max={key === "loss_rate" ? 90 : undefined} required={key === "unit_price"} defaultValue={item?.[key] ?? (key === "loss_rate" ? "0" : "")} /></Field>)}
        <Field label="计价单位"><select name="unit" defaultValue={item?.unit ?? "kg"}>
          {Object.entries(units).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></Field>
        <Field label="价格日期"><input name="price_date" type="date" defaultValue={item?.price_date ?? new Date().toLocaleDateString("sv-SE")} required /></Field>
      </div>
      <label className="check-row"><input type="checkbox" name="tax_included" defaultChecked={item?.tax_included} />报价含税</label>
      <ErrorLine error={action.error} /><div className="actions dialog-actions"><Button onClick={close}>取消</Button>
        <Button type="submit" variant="primary" busy={action.busy}>保存报价</Button></div>
    </form>
  </Modal>;
}
