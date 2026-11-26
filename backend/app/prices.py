from datetime import date, datetime
from io import BytesIO
from typing import Annotated, Literal
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from defusedxml.common import DefusedXmlException
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from pydantic import Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import admin, member
from app.core import Input, audit, database, fail, json_fields
from app.material_schema import Money, Positive
from app.models import MaterialPrice, User

router = APIRouter(tags=["材料报价"])
Unit = Literal["kg", "piece", "m2", "m"]
HEADERS = {
    "name": "材料名称", "grade": "材料牌号", "spec": "规格", "density": "密度(g/cm³)",
    "unit_price": "采购单价(元)", "unit": "计价单位", "loss_rate": "材料损耗率(%)",
    "process": "加工工艺", "process_price": "加工参考价(元/件)", "supplier": "供应商",
    "source": "价格来源", "price_date": "价格日期", "tax_included": "含税",
}
KEY_FIELDS = ("name", "grade", "spec", "process", "supplier")
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSX_LIMIT = 8 * 1024 * 1024


class PriceInput(Input):
    name: str = Field(min_length=1, max_length=100)
    grade: str = Field(default="", max_length=80)
    spec: str = Field(default="", max_length=120)
    density: Positive | None = None
    unit_price: Money
    unit: Unit = "kg"
    loss_rate: Money = Field(default=0, le=90)
    process: str = Field(default="", max_length=120)
    process_price: Money | None = None
    supplier: str = Field(default="", max_length=120)
    source: str = Field(min_length=1, max_length=160)
    price_date: date
    tax_included: bool = False


def price_view(row: MaterialPrice):
    return json_fields(row, "id", *HEADERS, "created_at", "updated_at")


@router.get("/material-prices")
def list_prices(q: str = Query("", max_length=120), offset: int = Query(0, ge=0),
                limit: int = Query(60, ge=1, le=250), db: Session = Depends(database), _: User = Depends(member)):
    query = select(MaterialPrice)
    if q.strip():
        query = query.where(MaterialPrice.name.icontains(q.strip(), autoescape=True) |
                            MaterialPrice.grade.icontains(q.strip(), autoescape=True) |
                            MaterialPrice.supplier.icontains(q.strip(), autoescape=True))
    rows = db.scalars(query.order_by(MaterialPrice.price_date.desc(), MaterialPrice.name, MaterialPrice.id)
                      .offset(offset).limit(limit + 1)).all()
    return {"items": [price_view(row) for row in rows[:limit]], "more": len(rows) > limit}


def write_price(db, actor, body, price=None):
    row = price or MaterialPrice()
    for field, value in body.model_dump(mode="json").items():
        setattr(row, field, value)
    db.add(row)
    db.flush()
    audit(db, actor, "price.saved", row.id)
    db.commit()
    return price_view(row)


@router.post("/admin/prices", status_code=201)
def create_price(body: PriceInput, db: Session = Depends(database), actor: User = Depends(admin)):
    return write_price(db, actor, body)


@router.put("/admin/prices/{price_id}")
def update_price(price_id: str, body: PriceInput, db: Session = Depends(database), actor: User = Depends(admin)):
    row = db.get(MaterialPrice, price_id, with_for_update=True)
    if not row:
        fail(404, "价格记录不存在")
    return write_price(db, actor, body, row)


@router.get("/admin/prices/export")
def export_prices(template: bool = False, db: Session = Depends(database), _: User = Depends(admin)):
    book = Workbook()
    sheet = book.active
    sheet.title = "材料价格"
    sheet.append(list(HEADERS.values()))
    sheet.freeze_panes = "A2"
    for column in sheet.columns:
        sheet.column_dimensions[column[0].column_letter].width = 21
    if not template:
        for row in db.scalars(select(MaterialPrice).order_by(MaterialPrice.name, MaterialPrice.grade)):
            sheet.append([getattr(row, field) for field in HEADERS])
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
    output = BytesIO()
    book.save(output)
    filename = "forma-price-template.xlsx" if template else "forma-prices.xlsx"
    return Response(output.getvalue(), media_type=XLSX_TYPE, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def read_prices(raw: bytes):
    if not raw or len(raw) > XLSX_LIMIT:
        fail(413, "Excel 文件上限为 8 MB")
    try:
        with ZipFile(BytesIO(raw)) as bundle:
            entries = bundle.infolist()
            if len(entries) > 500 or sum(entry.file_size for entry in entries) > 30 * 1024 * 1024:
                fail(413, "Excel 解压后的内容超过限制")
        book = load_workbook(BytesIO(raw), read_only=True, keep_links=False, data_only=False)
        try:
            sheet = book.active
            if sheet is None or (sheet.max_column or 0) > len(HEADERS) or (sheet.max_row or 0) > 5001:
                fail(422, "请使用导入模板，单次最多 5000 条价格")
            rows = sheet.iter_rows(max_col=len(HEADERS), max_row=sheet.max_row or 5002)
            if [cell.value for cell in next(rows, [])] != list(HEADERS.values()):
                fail(422, "Excel 标题行与模板不一致，请下载导入模板")
            items = []
            for index, cells in enumerate(rows, 2):
                if index > 5001:
                    fail(422, "单次最多导入 5000 条价格")
                if any(cell.data_type == "f" for cell in cells):
                    fail(422, f"第 {index} 行含公式，请粘贴计算后的值")
                if not any(cell.value is not None for cell in cells):
                    continue
                values = {key: cell.value for key, cell in zip(HEADERS, cells, strict=True) if cell.value is not None}
                if isinstance(values.get("price_date"), datetime):
                    values["price_date"] = values["price_date"].date()
                try:
                    items.append(PriceInput.model_validate(values))
                except ValidationError as error:
                    fail(422, f"第 {index} 行字段有误 · " + "、".join(str(item["loc"][0]) for item in error.errors()))
            return items
        finally:
            book.close()
    except (BadZipFile, DefusedXmlException, ParseError, OSError, KeyError, TypeError, ValueError):
        fail(422, "无法读取 Excel，请提供标准 .xlsx 文件")


@router.post("/admin/prices/import")
def import_prices(file: Annotated[UploadFile, File()], db: Session = Depends(database), actor: User = Depends(admin)):
    items = read_prices(file.file.read(XLSX_LIMIT + 1))
    if not items:
        fail(422, "文件中没有价格记录")
    current = {tuple(getattr(row, key) for key in KEY_FIELDS): row for row in db.scalars(select(MaterialPrice))}
    created = updated = 0
    for item in items:
        data = item.model_dump(mode="json")
        key = tuple(data[field] for field in KEY_FIELDS)
        if key in current:
            for field, value in data.items():
                setattr(current[key], field, value)
            updated += 1
        else:
            row = MaterialPrice(**data)
            current[key] = row
            db.add(row)
            created += 1
    audit(db, actor, "price.imported", created=created, updated=updated)
    db.commit()
    return {"created": created, "updated": updated}
