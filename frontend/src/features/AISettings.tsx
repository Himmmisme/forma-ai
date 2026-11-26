import { FlaskConical, PencilLine, Plus } from "lucide-react";
import { useState } from "react";
import { api, useAction, useResource, useSubmission } from "../api";
import { type Capability, type Job, type Model, type Protocol, type Provider, type Task, type Template,
  capabilityNames, taskNames } from "../types";
import { Button, Empty, ErrorLine, Field, IconButton, Loading, Modal } from "../ui";
import { JobItem } from "./Jobs";

const protocols: Record<Protocol, string> = { mock: "Mock", openai: "OpenAI 官方", gemini: "Gemini 官方", compatible: "OpenAI Compatible" };
interface AdminCatalog { providers: Provider[]; models: Model[]; bindings: Partial<Record<Task, string>> }
type ConfigDialog = { type: "provider"; item?: Provider } | { type: "model"; item?: Model } |
  { type: "probe"; provider?: Provider; model?: Model };
type Save = { close: () => void; saved: () => void };

export function AISettings() {
  const resource = useResource<AdminCatalog>("/admin/catalog");
  const bindingAction = useAction();
  const [dialog, setDialog] = useState<ConfigDialog>();
  const close = () => setDialog(undefined);
  const saved = () => { close(); resource.refresh(); };
  if (!resource.data) return <><ErrorLine error={resource.error} />{resource.loading && <Loading />}</>;
  const { providers, models, bindings } = resource.data;
  return <div className="form-stack">
    <section className="panel">
      <div className="section-heading"><div><h2>服务商</h2><p>管理 HTTPS 连接、凭据、超时和并发。</p></div>
        <Button variant="primary" onClick={() => setDialog({ type: "provider" })}><Plus size={16} />添加服务商</Button>
      </div>
      <ErrorLine error={resource.error} />
      <div className="table-scroll"><table>
        <thead><tr><th>服务商</th><th>协议</th><th>并发 / 超时</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>{providers.map((provider) => <tr key={provider.id}>
          <td><strong>{provider.name}</strong><small>{provider.base_url || "本地"}</small></td><td>{protocols[provider.protocol]}</td>
          <td>{provider.concurrency} / {provider.timeout}s</td><td>{provider.enabled ? "启用" : "禁用"}{provider.has_key && <small>已加密保存 Key</small>}</td>
          <td><div className="actions">
            {provider.protocol !== "mock" && <IconButton title={`编辑 ${provider.name}`} onClick={() => setDialog({ type: "provider", item: provider })}><PencilLine size={16} /></IconButton>}
            <Button disabled={!provider.enabled} onClick={() => setDialog({ type: "probe", provider })}><FlaskConical size={15} />连接测试</Button>
          </div></td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel">
      <div className="section-heading"><div><h2>模型</h2><p>使用供应商文档和能力测试确认模型 ID 及输入输出限制。</p></div>
        <Button variant="primary" disabled={!providers.some((item) => item.protocol !== "mock")} onClick={() => setDialog({ type: "model" })}><Plus size={16} />添加模型</Button>
      </div>
      <div className="table-scroll"><table>
        <thead><tr><th>模型</th><th>服务商</th><th>能力</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>{models.map((model) => <tr key={model.id}>
          <td><strong>{model.name}</strong><small>{model.model_code}</small></td><td>{model.provider_name}</td>
          <td>{model.capabilities.map((key) => capabilityNames[key]).join("、")}</td><td>{model.enabled ? "启用" : "禁用"}</td>
          <td><div className="actions">
            {model.protocol !== "mock" && <IconButton title={`编辑 ${model.name}`} onClick={() => setDialog({ type: "model", item: model })}><PencilLine size={16} /></IconButton>}
            <Button disabled={!model.enabled || !model.provider_enabled} onClick={() => setDialog({ type: "probe", model })}><FlaskConical size={15} />能力测试</Button>
          </div></td>
        </tr>)}</tbody>
      </table></div>
    </section>
    <section className="panel form-stack">
      <div><h2>任务默认模型</h2><p className="subtle compact">在任务入口确认后，所选输入才会发往外部服务。</p></div>
      <div className="form-grid">{Object.entries(taskNames).map(([key, label]) => {
        const task = key as Task;
        const required = task === "generate" ? "image_generate" : task === "edit" ? "image_edit" : task === "optimize" ? "text" : "vision";
        const eligible = models.filter((model) => model.enabled && model.provider_enabled && model.protocol !== "mock"
          && model.capabilities.includes(required)
          && (task !== "generate" || model.protocol === "gemini" || model.capabilities.includes("image_edit")));
        return <Field key={key} label={label}><select value={bindings[task] ?? ""} disabled={bindingAction.busy}
          onChange={(event) => {
            const id = event.target.value;
            void bindingAction.run(async () => { await api(`/admin/bindings/${task}`, "PUT", { model_id: id || null }); resource.refresh(); });
          }}>
          <option value="">默认 Mock</option>
          {bindings[task] && !eligible.some((model) => model.id === bindings[task]) && <option value={bindings[task]}>当前绑定不可用</option>}
          {eligible.map((model) => <option key={model.id} value={model.id}>{model.name} · {model.provider_name}</option>)}
        </select></Field>;
      })}</div>
      <ErrorLine error={bindingAction.error} />
    </section>
    {dialog?.type === "provider" && <ProviderEditor item={dialog.item} close={close} saved={saved} />}
    {dialog?.type === "model" && <ModelEditor item={dialog.item} providers={providers.filter((item) => item.protocol !== "mock")} close={close} saved={saved} />}
    {dialog?.type === "probe" && <ProbeDialog provider={dialog.provider} model={dialog.model} close={close} />}
  </div>;
}

function ProviderEditor({ item, close, saved }: Save & { item?: Provider }) {
  const [protocol, setProtocol] = useState(item?.protocol ?? "openai");
  const action = useAction();
  return <Modal title={item ? "编辑服务商" : "添加服务商"} onClose={close}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      void action.run(async () => {
        await api(item ? `/admin/providers/${item.id}` : "/admin/providers", item ? "PUT" : "POST", {
          name: values.get("name"), protocol, base_url: values.get("base_url") ?? "",
          api_key: values.get("key") || null, timeout: Number(values.get("timeout")),
          concurrency: Number(values.get("concurrency")), enabled: values.has("enabled"),
        });
        saved();
      });
    }}>
      <Field label="服务商名称"><input name="name" defaultValue={item?.name} required maxLength={80} /></Field>
      <Field label="协议"><select value={protocol} disabled={!!item} onChange={(event) => setProtocol(event.target.value as Protocol)}>
        {Object.entries(protocols).filter(([key]) => key !== "mock").map(([key, name]) => <option key={key} value={key}>{name}</option>)}
      </select></Field>
      {protocol === "compatible" && <Field label="Base URL" hint="公网 HTTPS API 前缀，如 https://api.example.com/v1">
        <input name="base_url" type="url" defaultValue={item?.base_url} maxLength={512} required />
      </Field>}
      <Field label="API Key" hint={item?.has_key ? "已加密保存。留空保留当前 Key。" : "凭据将使用实例独立密钥加密。"}>
        <input name="key" type="password" autoComplete="new-password" maxLength={4096} />
      </Field>
      <div className="form-grid">
        <Field label="请求超时（秒）"><input name="timeout" type="number" min={5} max={180} required defaultValue={item?.timeout ?? 120} /></Field>
        <Field label="最大并发"><input name="concurrency" type="number" min={1} max={8} required defaultValue={item?.concurrency ?? 1} /></Field>
      </div>
      <label className="check-row"><input name="enabled" type="checkbox" defaultChecked={item?.enabled ?? true} />启用服务商</label>
      <ErrorLine error={action.error} /><SaveButtons close={close} busy={action.busy} />
    </form>
  </Modal>;
}

function ModelEditor({ item, providers, close, saved }: Save & { item?: Model; providers: Provider[] }) {
  const action = useAction();
  return <Modal title={item ? "编辑模型" : "添加模型"} onClose={close}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      const sizes = String(values.get("sizes") ?? "").split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
        const [ratio, label, value] = line.split("|").map((part) => part.trim());
        return { ratio, label, value };
      });
      if (sizes.some((size) => !size.ratio || !size.label || !size.value)) { action.setError("请按每行 比例 | 显示名 | API 参数 填写输出规格"); return; }
      void action.run(async () => {
        await api(item ? `/admin/models/${item.id}` : "/admin/models", item ? "PUT" : "POST", {
          name: values.get("name"), provider_id: item?.provider_id ?? values.get("provider_id"),
          model_code: values.get("model_code"), capabilities: values.getAll("capabilities"), sizes,
          max_count: Number(values.get("max_count")), max_inputs: Number(values.get("max_inputs")),
          pricing: values.get("pricing"), enabled: values.has("enabled"),
        });
        saved();
      });
    }}>
      <div className="form-grid">
        <Field label="显示名称"><input name="name" maxLength={80} defaultValue={item?.name} required /></Field>
        <Field label="服务商"><select name="provider_id" defaultValue={item?.provider_id} disabled={!!item}>
          {providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}
        </select></Field>
      </div>
      <Field label="供应商模型 ID"><input name="model_code" maxLength={120} defaultValue={item?.model_code} required /></Field>
      <fieldset><legend>模型能力</legend><div className="actions">
        {Object.entries(capabilityNames).map(([key, label]) => <label key={key} className="check-row">
          <input type="checkbox" name="capabilities" value={key} defaultChecked={item?.capabilities.includes(key as Capability)} />{label}
        </label>)}
      </div></fieldset>
      <Field label="图片规格" hint="每行填写 比例 | 显示名 | API 参数。例 1:1 | 1024 × 1024 | 1024x1024。Gemini 使用模型支持的 imageSize，default 表示省略。">
        <textarea name="sizes" rows={4} defaultValue={item?.sizes.map((size) => `${size.ratio} | ${size.label} | ${size.value}`).join("\n")} />
      </Field>
      <div className="form-grid">
        <Field label="每次最大生成张数"><input name="max_count" type="number" min={1} max={4} defaultValue={item?.max_count ?? 1} required /></Field>
        <Field label="每次最大输入张数"><input name="max_inputs" type="number" min={1} max={16} defaultValue={item?.max_inputs ?? 1} required /></Field>
      </div>
      <Field label="价格与计费规则"><textarea name="pricing" rows={2} maxLength={3000} defaultValue={item?.pricing} /></Field>
      <label className="check-row"><input type="checkbox" name="enabled" defaultChecked={item?.enabled ?? true} />启用模型</label>
      <ErrorLine error={action.error} /><SaveButtons close={close} busy={action.busy} />
    </form>
  </Modal>;
}

function ProbeDialog({ provider, model, close }: { provider?: Provider; model?: Model; close: () => void }) {
  const [id, setId] = useState("");
  const [capability, setCapability] = useState(model?.capabilities[0] ?? "text");
  const [confirm, setConfirm] = useState(false);
  const remote = (provider?.protocol ?? model?.protocol) !== "mock";
  const current = useResource<Job>(id ? `/jobs/${id}` : null, 1300);
  const action = useAction();
  const submit = useSubmission();
  return <Modal title={provider ? "测试服务商连接" : "测试模型能力"} onClose={close}>
    <div className="form-stack">
      <p>{provider?.name ?? model?.name}</p>
      {model && <Field label="测试能力"><select value={capability} onChange={(event) => setCapability(event.target.value as Capability)}>
        {model.capabilities.map((key) => <option key={key} value={key}>{capabilityNames[key]}</option>)}
      </select></Field>}
      {remote && <label className="check-row notice warning"><input type="checkbox" checked={confirm}
        onChange={(event) => setConfirm(event.target.checked)} />同意发起外部测试请求。模型测试可能产生费用。</label>}
      <Button variant="primary" busy={action.busy} disabled={remote && !confirm || current.loading ||
        current.data?.status === "running" || current.data?.status === "queued"}
        onClick={() => void action.run(async () => {
          const route = provider ? `/admin/providers/${provider.id}/test` : `/admin/models/${model!.id}/test`;
          setId((await submit<Job>(route, { ack_external: confirm, ...(model && { capability }) })).id);
        })}><FlaskConical size={16} />运行测试</Button>
      <ErrorLine error={action.error || current.error} />
      {current.loading && <Loading />}{current.data && <JobItem job={current.data} refresh={current.refresh} />}
    </div>
  </Modal>;
}

export function TemplatesPanel() {
  const templates = useResource<Template[]>("/admin/templates");
  const [kind, setKind] = useState("direction");
  const [editor, setEditor] = useState<{ row?: Template }>();
  const items = templates.data?.filter((row) => row.kind === kind);
  return <section className="panel">
    <div className="section-heading"><div><h2>提示词模板</h2><p>编辑后保存为新的修订，已生成版本保留其实际模板。</p></div>
      {kind === "direction" && <Button variant="primary" onClick={() => setEditor({})}><Plus size={16} />添加方向</Button>}
    </div>
    <div className="tabs"><button className={kind === "direction" ? "active" : ""} onClick={() => setKind("direction")}>执行方向</button>
      <button className={kind === "level" ? "active" : ""} onClick={() => setKind("level")}>重构档位</button></div>
    <ErrorLine error={templates.error} />{templates.loading && <Loading />}
    {items?.length === 0 && <Empty title="没有模板" />}
    {!!items?.length && <div className="table-scroll top-gap"><table>
      <thead><tr><th>名称</th><th>顺序</th><th>修订</th><th>状态</th><th>编辑</th></tr></thead>
      <tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.slug} · {item.summary}</small></td>
        <td>{item.sort}</td><td>{item.revision}</td><td>{item.enabled ? "启用" : "禁用"}</td>
        <td><IconButton title={`编辑 ${item.name}`} onClick={() => setEditor({ row: item })}><PencilLine size={16} /></IconButton></td>
      </tr>)}</tbody>
    </table></div>}
    {editor && <TemplateEditor item={editor.row} close={() => setEditor(undefined)}
      saved={() => { setEditor(undefined); templates.refresh(); }} />}
  </section>;
}

function TemplateEditor({ item, close, saved }: Save & { item?: Template }) {
  const action = useAction();
  return <Modal title={item ? "编辑提示词模板" : "添加设计方向"} onClose={close}>
    <form className="form-stack" onSubmit={(event) => {
      event.preventDefault();
      const values = new FormData(event.currentTarget);
      void action.run(async () => {
        await api(item ? `/admin/templates/${item.id}` : "/admin/templates", item ? "PUT" : "POST", {
          name: values.get("name"), summary: values.get("summary"), body: values.get("body"),
          sort: Number(values.get("sort")), enabled: item?.kind === "level" || values.has("enabled"),
          ...(!item && { slug: values.get("slug") }),
        });
        saved();
      });
    }}>
      {!item && <Field label="标识符"><input name="slug" placeholder="例如 surface-detail" maxLength={48} required /></Field>}
      <Field label="名称"><input name="name" maxLength={80} defaultValue={item?.name} required /></Field>
      <Field label="简述"><input name="summary" maxLength={240} defaultValue={item?.summary} required /></Field>
      <Field label="提示词正文"><textarea name="body" maxLength={3600} rows={6} defaultValue={item?.body} required /></Field>
      <Field label="排序数值"><input name="sort" type="number" defaultValue={item?.sort ?? 100} min={-10000} max={10000} required /></Field>
      {item?.kind !== "level" && <label className="check-row"><input type="checkbox" name="enabled" defaultChecked={item?.enabled ?? true} />启用</label>}
      <ErrorLine error={action.error} /><SaveButtons close={close} busy={action.busy} />
    </form>
  </Modal>;
}

function SaveButtons({ close, busy }: { close: () => void; busy: boolean }) {
  return <div className="actions dialog-actions"><Button onClick={close}>取消</Button><Button type="submit" variant="primary" busy={busy}>保存</Button></div>;
}
