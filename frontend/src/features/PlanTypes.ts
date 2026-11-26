import type { Job } from "../types";
import type { Price, Unit } from "./Prices";

export interface Component {
  name: string; function: string; material: string; grade: string; spec: string; process: string; finish: string;
  reason: string; alternatives: string[]; quantity_estimate: string; estimated_weight_kg: string | null;
  ai_price_kg: string | null; risk: string; savings: string; assumptions: string;
}
export interface Materials { summary: string; components: Component[]; uncertainties: string[]; cost_suggestions: string[] }
export interface Plan<T> { id: string; name: string; data: T; job_id?: string; updated_at: string }
export interface Part {
  name: string; material: string; grade: string; process: string; per_product: string;
  length: string | null; width: string | null; height: string | null; thickness: string | null; weight_kg: string | null;
  estimated_weight_kg: string | null; density: string | null; price_id: string | null; unit_price: string | null;
  unit: Unit; ai_price_kg: string | null; loss_percent: string | null; process_price: string | null; finish_price: string | null;
}
export interface CostDraft {
  name: string; material_plan_id: string | null; parts: Part[]; quantity: string;
  length: string | null; width: string | null; height: string | null; tooling: string; assembly: string; hardware: string;
  electronics: string; include_electronics: boolean; target: string | null; tax_included: boolean;
  tax_rate: string | null; margin: string; notes: string;
}
export interface BOM {
  name: string; material: string; grade: string; process: string; per_product: number; source: string;
  process_source: string; unit: Unit; unit_price: string | null; weight_kg: string | null; purchase: string | null;
  loss_percent: string; raw: string | null; processing: string | null; surface: string | null; total: string;
  missing: string[]; assumptions: string[]; library: Price | null;
}
export interface CostResult {
  quantity: number; partial: boolean; tax_included: boolean; include_electronics: boolean;
  unit_material: string; unit_processing: string; unit_surface: string; unit_assembly: string; unit_hardware: string;
  unit_electronics: string; unit_tooling: string; unit_manufacturing: string; batch_total: string; tooling: string;
  range: [string, string]; target_gap: string | null; bom: BOM[]; basis: string[]; suggestions: string[];
}
export type CostPlan = Plan<{ inputs: CostDraft; result: CostResult }>;
export interface AnalysisData {
  materials: Plan<Materials>[]; costs: CostPlan[];
  jobs: (Omit<Job, "result"> & { result: (Job["result"] & Partial<Materials>) | null })[];
}
