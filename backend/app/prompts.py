from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import fail, json_fields
from app.models import Asset, PromptTemplate

BASE_REVISION = "1.0"
BASE = """你是一名工业产品设计师。根据输入图像和设计任务输出产品概念设计。
保持功能区域可辨认，结合握持、操作、清洁与维护路径考虑整体形态及比例。以合理的倒角与转角半径处理接触边缘。
说明分件必须通过可见的壳体接缝和装配边界表达。材质、颜色、纹理及反射应符合工艺预期。
草案只表达概念，未经测量不得推断精确尺寸、载荷、内部布局或工程可行性。用户明确保留项具有最高优先级。"""

DIRECTIONS = [
    ("form", "造型焕新", "重整轮廓、比例和体块关系。", "先识别正侧面的主体体块与受力底面。以稳定的体量关系重塑轮廓，利用连续曲率、明确的特征线与可制造的分件建立视觉识别。"),
    ("refine", "外观优化", "校正视觉重心与局部细节。", "保留产品架构，优化缝隙走向、按键高低差和边缘圆角。统一相邻表面曲率与装配边界，保证指示区和接口可达。"),
    ("cmf", "CMF 设计", "统一颜色、材料与表面工艺。", "按耐磨接触区、主壳、透光件和装饰件规划 CMF。明确颜色层级、光泽差异、纹理方向和适于量产的表面处理，控制色差及缩水可见性。"),
    ("tech", "科技感升级", "以精准分件和功能表达建立技术感。", "使用清晰的功能分区、精确的接合和一致的纹理节奏营造技术感。保留原有输入输出界面，新增显示或灯光需由明确需求授权。"),
    ("minimal", "极简化设计", "减少视觉噪声，保留操作识别。", "合并装饰特征、收敛轮廓与色彩，隐藏非维护区域的紧固件。通过触觉、位置和对比度保留操作与安全标识的识别性。"),
    ("premium", "高端化设计", "强化材质真实感及细节一致性。", "控制壳体接缝齐平和触感，使用有实际工艺依据的铝合金、细纹聚合物或其它适用材料。避免镜面在频繁接触区域放大污渍。"),
    ("family", "产品系列化", "建立跨规格复用的设计语言。", "提取识别特征并区分共享语言与可变区。常用界面布置一致，优先考虑可复用外壳区段、紧固件及装配方式。"),
    ("reference", "参考图融合", "提炼参考特征并适配原产品。", "只提炼参考图的体块关系、表面处理或分缝逻辑。以原产品功能区和装配边界约束转译策略，参考图中的功能由原产品约束决定。"),
    ("cost", "成本优化设计", "降低零件、模具和工艺复杂度。", "减少零件和重复工序，优先考虑常用材料、均匀壁厚、拔模方向与常见紧固件。仍需保留维护路径及人机接触要求。"),
    ("structure", "结构概念创新", "探索分件、模块化和维护方式。", "针对可见的连接、开合和维护需求提出概念结构，考虑装配方向、工具空间和可替换模块。未知内部结构以待确认前提处理。"),
]
LEVELS = [
    ("l1", "微调优化", "仅调整颜色、材质及局部细节。", "严格保持整体轮廓、功能界面、件间关系和开孔位置。只改变颜色、表面质感与有限局部特征。"),
    ("l2", "轻度重构", "保持整体轮廓，优化线条及局部比例。", "保持主要投影轮廓和功能区域。允许调整外壳线条、圆角、视觉接缝和小范围局部比例。"),
    ("l3", "中度重构", "保留核心功能布局，重做外壳及视觉语言。", "核心功能区域、接口及操作路径保持。允许重新组织外壳、分件、配色和整体视觉语言。"),
    ("l4", "深度重构", "允许调整形态、外观布局及结构概念。", "可显著改变体块、部件外观布局和分件结构概念。验证保留项与可见功能存在可制造的设计落点。"),
    ("l5", "概念重塑", "围绕核心功能探索全新造型。", "从核心用途、操作路径和场景重新探索产品构型。仅在保留用户指定区域及约束的前提下打破原外壳结构。"),
]
BACKGROUNDS = {"studio": "浅灰中性摄影棚背景", "white": "纯白目录拍摄背景", "dark": "深灰中性摄影棚背景", "context": "贴合真实使用场景，保持主体突出"}
VIEWS = {"three_quarter": "三分之四视角", "front": "正视角", "side": "侧视角", "top": "俯视角"}


def template_view(template: PromptTemplate):
    return json_fields(template, "id", "slug", "kind", "name", "summary", "body", "sort", "enabled", "revision")


def get_templates(db: Session, ids: list[str], kind: str) -> list[PromptTemplate]:
    rows = {row.id: row for row in db.scalars(select(PromptTemplate).where(
        PromptTemplate.id.in_(ids), PromptTemplate.kind == kind, PromptTemplate.enabled
    ))}
    if len(rows) != len(ids):
        fail(422, "提示词模板已停用、重复或不存在，请重新选择")
    return [rows[item] for item in ids]


def conflict_hints(raw: str, final: str, constraints: str, level: str, directions: list[PromptTemplate], refs: list):
    warnings = []
    protected = ("整体轮廓", "外壳", "接口", "开孔", "按键", "屏幕", "装配", "尺寸", "底座", "通风口", "镜头", "手柄")
    source = f"{raw}\n{final}"
    for part in protected:
        kept = part in constraints or any(word + part in source for word in ("保留", "保持", "维持", "不改变"))
        changed = any(word + part in source for word in ("去掉", "移除", "取消", "删除", "重新设计", "替换", "移动"))
        if kept and changed:
            warnings.append(f"需求同时要求保留和修改「{part}」。提交后按明确保留项处理。")
    if constraints and level in {"l4", "l5"}:
        warnings.append("深度重构可能与保留项交叉。保留项优先，重构只作用于其余区域。")
    if level == "l1" and any(row.slug in {"structure", "form"} for row in directions):
        warnings.append("微调档位限制明显的造型或结构变化。方向模板将在 L1 约束内应用。")
    if any(row.slug == "reference" for row in directions) and not refs:
        warnings.append("已选择参考图融合，当前没有选入参考图。")
    return warnings


def compose(
    *, original: list[Asset], references: list[Asset], iteration: Asset | None, directions: list[PromptTemplate],
    level: PromptTemplate, raw: str, optimized: str, final: str, constraints: str, output: dict,
):
    text = [f"工业设计基础约束 {BASE_REVISION}\n{BASE}",
            f"原图 · {len(original)} 张。用原图验证产品体块、功能区域和各角度的一致性。"]
    if iteration:
        text.append("迭代输入 · 首张图片为当前设计版本。继承该版本造型，仅按本轮需求改变；后续原图用于功能校对。")
    text.append(f"主方向 · {directions[0].name}\n{directions[0].body}")
    if len(directions) > 1:
        text.append("辅助方向\n" + "\n".join(f"{row.name} · {row.body}" for row in directions[1:]))
    text.append(f"重构幅度 · {level.name}\n{level.body}")
    if references:
        text.append(f"参考图 · 最后 {len(references)} 张。只用于参考明确要求的外观、材质和设计语言。原图功能和保留项优先。")
    text.append("用户最终需求\n" + (final or optimized or raw or "按所选方向与重构档位执行。"))
    if raw and raw != (final or optimized):
        text.append("原始需求用作补充语境，冲突处以最终需求及明确保留项为准。\n" + raw)
    text.append("用户保留约束 · 优先执行\n" + (constraints or "按产品原图和重构幅度保留功能边界。"))
    text.append(f"输出 · {VIEWS[output['view']]}，{BACKGROUNDS[output['background']]}，比例 {output['ratio']}。"
                "展示完整产品，保留轮廓空间。画面只含产品概念实拍风格图，无水印、尺寸标注和未经授权的品牌。")
    return "\n\n".join(text)
