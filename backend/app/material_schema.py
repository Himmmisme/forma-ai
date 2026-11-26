from decimal import Decimal
from typing import Annotated

from pydantic import Field, StringConstraints

from app.core import Input

Money = Annotated[Decimal, Field(ge=0, le=1_000_000_000, max_digits=16, decimal_places=6)]
Positive = Annotated[Decimal, Field(gt=0, le=1_000_000, max_digits=14, decimal_places=6)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=8, decimal_places=4)]
Notes = Annotated[str, StringConstraints(max_length=1200)]


class Component(Input):
    name: str = Field(min_length=1, max_length=120)
    function: Notes = ""
    material: str = Field(min_length=1, max_length=100)
    grade: str = Field(default="", max_length=80)
    spec: Notes = ""
    process: Notes = ""
    finish: Notes = ""
    reason: Notes = ""
    alternatives: list[Notes] = Field(default_factory=list, max_length=8)
    quantity_estimate: Notes = ""
    estimated_weight_kg: Positive | None = None
    ai_price_kg: Money | None = None
    risk: Notes = ""
    savings: Notes = ""
    assumptions: Notes = ""


class MaterialData(Input):
    summary: Notes = ""
    components: list[Component] = Field(min_length=1, max_length=30)
    uncertainties: list[Notes] = Field(default_factory=list, max_length=20)
    cost_suggestions: list[Notes] = Field(default_factory=list, max_length=20)


MATERIAL_PROMPT = """分析所附二维工业设计成果，识别可见部件并用中文给出概念级材料选型建议。
针对触感、刚度、耐磨、可见接缝和可制造性比较选择，适用时考虑 ABS、PC、PC+ABS、PMMA、冷轧钢、不锈钢和铝合金。
输出 JSON 对象：summary 字符串，uncertainties 和 cost_suggestions 为字符串数组，components 为对象数组。
每个部件包含字符串 name（名称）、function（作用）、material、grade（牌号）、spec（厚度或规格）、process、
finish、reason、quantity_estimate、risk、savings、assumptions，alternatives 为字符串数组。
可选数字 estimated_weight_kg 和 ai_price_kg 分别为有明确前提的 kg 估算和元/kg 参考估价，无依据时给 null。
一张二维图不能确认的尺寸、重量、内部结构、牌号与工艺条件须明确写待确认或估算。报价不是采购价格。"""

MOCK_MATERIALS = {
    "summary": "Mock 概念方案。以下部件和材料是通用示例，请按实际设计图调整。",
    "components": [
        {"name": "主体外壳", "function": "覆盖及保护设备", "material": "PC+ABS", "grade": "耐冲击级待确认",
         "spec": "约 2–3 mm，按刚度与拔模校核", "process": "注塑", "finish": "细纹哑光",
         "reason": "可同时考虑冲击韧性与复杂壳体的注塑成形",
         "alternatives": ["ABS", "5052 铝合金"], "quantity_estimate": "每台 1 件，重量待确认",
         "risk": "转角和立筋附近可能出现缩水或翘曲", "savings": "统一壁厚，减少重复表面处理",
         "assumptions": "内筋、耐候和阻燃等级待确认"},
        {"name": "可见面盖", "function": "形成前部外观及操作边界", "material": "铝合金", "grade": "5052（概念建议）",
         "spec": "约 1 mm，待验证", "process": "冲压与整形", "finish": "细纹粉末涂层",
         "reason": "适用于较薄面件并可通过涂层统一外观",
         "alternatives": ["冷轧钢板 SPCC", "ABS"], "quantity_estimate": "每台 1 件，面积和质量待确认",
         "risk": "孔边变形和安装干涉需样件验证", "savings": "统一开孔与紧固件规格", "assumptions": "只假设有可见面盖"},
    ],
    "uncertainties": ["内部结构、部件重量和真实尺寸需要 CAD 或实测确认。"],
    "cost_suggestions": ["先用量产件展开面积、样件重量与供应商实际报价替换概念假设。"],
}
