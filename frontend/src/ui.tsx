import { Box, CircleAlert, ImageIcon, LoaderCircle, X } from "lucide-react";
import { type ButtonHTMLAttributes, type PropsWithChildren, type ReactNode, useEffect, useRef } from "react";
import { assetUrl } from "./api";
import type { Asset } from "./types";

export function Brand() {
  return <div className="brand"><span className="brand-mark"><Box size={21} strokeWidth={2.1} /></span><span>Forma AI</span></div>;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; busy?: boolean };
export function Button({ variant = "secondary", busy, className = "", children, ...props }: ButtonProps) {
  return <button type="button" {...props} disabled={props.disabled || busy} className={`btn btn-${variant} ${className}`}>
    {busy && <LoaderCircle size={16} className="spin" aria-hidden />}{children}
  </button>;
}

export function IconButton({ title, children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { title: string }) {
  return <button type="button" {...props} title={title} aria-label={title} className={`icon-btn ${className}`}>{children}</button>;
}

export function Heading({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-heading"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="actions">{actions}</div>}</div>;
}

export function ErrorLine({ error }: { error?: string }) {
  return error ? <div className="notice danger" role="alert"><CircleAlert size={17} aria-hidden />{error}</div> : null;
}

export function Loading() {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={18} />加载中</div>;
}

export function Empty({ title, description, children, icon }: PropsWithChildren<{ title: string; description?: string; icon?: ReactNode }>) {
  return <div className="empty"><div className="empty-icon">{icon ?? <ImageIcon size={24} />}</div><h3>{title}</h3>
    {description && <p>{description}</p>}{children && <div className="actions">{children}</div>}
  </div>;
}

export function Modal({ title, onClose, children, wide = false }: PropsWithChildren<{ title: string; onClose: () => void; wide?: boolean }>) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return <dialog ref={dialog} className={wide ? "dialog wide-dialog" : "dialog"} aria-label={title}
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <div className="dialog-head"><h2>{title}</h2><IconButton title="关闭" onClick={onClose}><X size={20} /></IconButton></div>
    <div className="dialog-body">{children}</div>
  </dialog>;
}

export function Preview({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  return <Modal title={asset.filename} onClose={onClose} wide>
    <img className="full-preview" src={assetUrl(asset.id)} alt={asset.filename} />
    <div className="split-row modal-meta"><span>{asset.width} × {asset.height}</span>
      <a className="btn btn-secondary" href={assetUrl(asset.id, true)}>下载图片</a>
    </div>
  </Modal>;
}

export function Field({ label, hint, children }: PropsWithChildren<{ label: string; hint?: string }>) {
  return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}
