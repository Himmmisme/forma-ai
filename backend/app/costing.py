from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import Field
from sqlalchemy import select

from app.core import Input, fail
from app.material_schema import Money, Percent, Positive
from app.models import MaterialPrice
from app.prices import Unit, price_view

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)
DIMENSION = Decimal(1_000_000)


class CostPart(Input):
    name: str = Field(min_length=1, max_length=120)
    material: str = Field(min_length=1, max_length=100)
    grade: str = Field(default="", max_length=80)
    process: str = Field(default="", max_length=120)
    per_product: int = Field(default=1, ge=1, le=10000)
    length: Positive | None = None
    width: Positive | None = None
    height: Positive | None = None
    thickness: Positive | None = None
    weight_kg: Positive | None = None
    estimated_weight_kg: Positive | None = None
    density: Positive | None = None
    price_id: str | None = Field(default=None, max_length=32)
    unit_price: Money | None = None
    unit: Unit = "kg"
    ai_price_kg: Money | None = None
    loss_percent: Percent | None = Field(default=None, le=90)
    process_price: Money | None = None
    finish_price: Money | None = None


class CostInput(Input):
    name: str = Field(min_length=1, max_length=120)
    material_plan_id: str | None = Field(default=None, max_length=32)
    parts: list[CostPart] = Field(min_length=1, max_length=50)
    quantity: int = Field(default=1000, ge=1, le=10_000_000)
    length: Positive | None = None
    width: Positive | None = None
    height: Positive | None = None
    tooling: Money = Decimal(0)
    assembly: Money = Decimal(0)
    hardware: Money = Decimal(0)
    electronics: Money = Decimal(0)
    include_electronics: bool = False
    target: Money | None = None
    tax_included: bool = False
    tax_rate: Percent | None = None
    margin: Percent = Decimal(15)
    notes: str = Field(default="", max_length=3000)


def decimal(value):
    return Decimal(value) if value is not None else None


def fmt(value: Decimal, precision="0.01"):
    return format(value.quantize(Decimal(precision), rounding=ROUND_HALF_UP), "f")


def lookup(db, part):
    if part.price_id:
        library = db.get(MaterialPrice, part.price_id)
        if not library:
            fail(422, "所选材料价格不存在")
        return library
    criteria = [MaterialPrice.name == part.material]
    if part.grade:
        criteria.append(MaterialPrice.grade == part.grade)
    if part.process:
        matching = db.scalar(select(MaterialPrice).where(*criteria, MaterialPrice.process == part.process)
                             .order_by(MaterialPrice.price_date.desc(), MaterialPrice.id).limit(1))
        if matching:
            return matching
    return db.scalar(select(MaterialPrice).where(*criteria).order_by(MaterialPrice.price_date.desc(), MaterialPrice.id).limit(1))


def tax_adjust(amount, library, options, missing, label):
    if amount is None or library.tax_included == options.tax_included:
        return amount
    if options.tax_rate is None:
        missing.append(f"{label}的含税口径不同，请填写换算税率")
        return None
    factor = ONE + options.tax_rate / HUNDRED
    return amount * factor if options.tax_included else amount / factor


def estimate_part(db, part, inputs):
    library = lookup(db, part)
    assumptions, missing = [], []
    mass = part.weight_kg
    density = part.density or (decimal(library.density) if library else None)
    thickness = part.thickness or part.height
    if mass is None and density and part.length and part.width and thickness:
        mass = part.length * part.width * thickness * density / DIMENSION
        assumptions.append("质量按长×宽×厚度（或高度）实心近似，孔洞及曲面需实测校正")
    if mass is None and part.estimated_weight_kg is not None:
        mass = part.estimated_weight_kg
        assumptions.append("质量使用明确录入或采纳的参考估算")
    unit, price = part.unit, part.unit_price
    source = "用户采购输入"
    if price is None and library:
        unit = library.unit
        source = "材料价格库 · " + library.source
        price = tax_adjust(decimal(library.unit_price), library, inputs, missing, "采购价格")
    elif price is None and part.ai_price_kg is not None:
        unit, price, source = "kg", part.ai_price_kg, "AI 参考估价"
        assumptions.append("参考估价按本方案的税费口径填写，采购时需重新询价")
    elif price is None:
        source = "待确认"
        missing.append("缺少可用采购价格")
    loss = part.loss_percent if part.loss_percent is not None else (decimal(library.loss_rate) if library else ZERO)
    if part.loss_percent is None and not library:
        assumptions.append("未提供损耗率，暂按 0%")
    quantities = {"piece": ONE, "kg": mass, "m2": part.length * part.width / DIMENSION if part.length and part.width else None,
                  "m": part.length / Decimal(1000) if part.length else None}
    base = quantities[unit]
    if base is None:
        missing.append("缺少该计价单位所需的重量或尺寸")
    purchase = base / (ONE - loss / HUNDRED) * part.per_product if base is not None else None
    raw = purchase * price if purchase is not None and price is not None else None
    process = part.process_price
    process_source = "用户输入"
    if process is None and library and library.process_price is not None and (
        not part.process or part.process == library.process
    ):
        process_source = "材料价格库"
        process = tax_adjust(decimal(library.process_price), library, inputs, missing, "加工参考价")
    if process is None:
        missing.append("加工费待确认")
        process_source = "待确认"
    if part.finish_price is None:
        missing.append("表面处理费待确认")
    processing = process * part.per_product if process is not None else None
    surface = part.finish_price * part.per_product if part.finish_price is not None else None
    amounts = raw or ZERO, processing or ZERO, surface or ZERO
    metrics = {
        "name": part.name, "material": part.material, "grade": part.grade, "process": part.process,
        "per_product": part.per_product, "source": source, "unit": unit, "process_source": process_source,
        "unit_price": fmt(price, "0.0001") if price is not None else None, "loss_percent": str(loss),
        "purchase": fmt(purchase, "0.000001") if purchase is not None else None,
        "weight_kg": fmt(mass, "0.000001") if mass is not None else None,
        "raw": fmt(raw, "0.0001") if raw is not None else None,
        "processing": fmt(processing, "0.0001") if processing is not None else None,
        "surface": fmt(surface, "0.0001") if surface is not None else None,
        "total": fmt(sum(amounts), "0.0001"), "missing": missing, "assumptions": assumptions,
        "library": price_view(library) if library else None,
    }
    return metrics, amounts


def calculate(db, inputs: CostInput):
    with localcontext() as context:
        context.prec = 56
        return calculate_totals(db, inputs)


def calculate_totals(db, inputs: CostInput):
    bom = []
    material = processing = surface = ZERO
    for part in inputs.parts:
        line, values = estimate_part(db, part, inputs)
        bom.append(line)
        material += values[0]
        processing += values[1]
        surface += values[2]
    partial = any(line["missing"] for line in bom)
    electronics = inputs.electronics if inputs.include_electronics else ZERO
    variable = material + processing + surface + inputs.assembly + inputs.hardware + electronics
    mold_unit = inputs.tooling / inputs.quantity
    single = variable + mold_unit
    margin = inputs.margin / HUNDRED
    return {
        "currency": "CNY", "quantity": inputs.quantity, "partial": partial,
        "tax_included": inputs.tax_included, "include_electronics": inputs.include_electronics,
        "unit_material": fmt(material), "unit_processing": fmt(processing), "unit_surface": fmt(surface),
        "unit_assembly": fmt(inputs.assembly), "unit_hardware": fmt(inputs.hardware), "unit_electronics": fmt(electronics),
        "unit_tooling": fmt(mold_unit), "unit_manufacturing": fmt(single),
        "batch_total": fmt(variable * inputs.quantity + inputs.tooling), "tooling": fmt(inputs.tooling),
        "range": [fmt(variable * (ONE - margin) + mold_unit), fmt(variable * (ONE + margin) + mold_unit)],
        "target_gap": fmt(single - inputs.target) if inputs.target is not None else None,
        "bom": bom, "basis": [
            "按人民币计价。材料采购量按成品用量 ÷ (1 − 损耗率) 计算；零件费用乘以每台用量。",
            "材料报价按用户采购价、匹配价格库、AI 参考估价的顺序取用，并保留报价快照。",
            "单台制造成本含已填写的全部单台费用和模具分摊。批量总成本使用未提前舍入的行项目。",
            "成本区间只对已计入的可变费用应用用户填写的估算浮动，模具费用保持固定。",
            "运费、质检和管理费用须通过已列费用或估算说明明确计入。",
        ],
        "suggestions": ["优先与供应商核实明细中标记的缺项、损耗和税费口径。"] if partial else
                       ["对高占比部件复核材料用量、加工工序与供应商分档报价。"],
    }
