import io

from conftest import add_user
from openpyxl import load_workbook
from test_design import design_payload, execute_queued, new_project


def completed_version(owner, application):
    project, asset = new_project(owner)
    result = owner.post(f"/api/projects/{project}/generate", json=design_payload(owner, project, asset))
    assert result.status_code == 202
    job = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    return project, job["result"]["version_ids"][0]


def price_payload(**overrides):
    return {"name": "ABS", "grade": "A1", "spec": "颗粒", "density": "1.05", "unit_price": "20",
            "loss_rate": "20", "process": "注塑", "process_price": "1.2", "supplier": "测试供应商",
            "source": "测试报价记录", "price_date": "2026-01-15", **overrides}


def test_multiple_material_and_cost_plans(owner, application):
    project, vid = completed_version(owner, application)
    path = f"/api/versions/{vid}"
    ai = owner.post(path + "/analysis", json={"kind": "materials", "request_key": "forma-materials-key"})
    assert ai.status_code == 202, ai.text
    ai = owner.get(f"/api/jobs/{execute_queued(application)}").json()
    assert ai["status"] == "succeeded" and ai["mock"]
    data = ai["result"]
    assert data["uncertainties"] and data["components"][0]["estimated_weight_kg"] is None
    plan = owner.post(path + "/materials", json={"name": "概念方案", "job_id": ai["id"], "data": data})
    assert plan.status_code == 201, plan.text
    assert owner.post(path + "/materials", json={"name": "替代方案", "data": data}).status_code == 201

    price = owner.post("/api/admin/prices", json=price_payload())
    assert price.status_code == 201, price.text
    request = {"name": "量产估算", "material_plan_id": plan.json()["id"], "quantity": 1000,
               "tooling": "1000", "assembly": "1", "hardware": ".5", "electronics": "3",
               "include_electronics": True, "parts": [
                   {"name": "外壳", "material": "ABS", "grade": "A1", "process": "注塑", "per_product": 2,
                    "weight_kg": ".1", "finish_price": ".2", "ai_price_kg": "99"},
               ]}
    report = owner.post(path + "/costs", json=request)
    assert report.status_code == 201, report.text
    saved = report.json()
    result = saved["data"]["result"]
    assert not result["partial"]
    assert result["unit_material"] == "5.00"
    assert result["unit_manufacturing"] == "13.30"
    assert result["batch_total"] == "13300.00"
    assert result["bom"][0]["library"]["id"] == price.json()["id"]
    custom = owner.put(path + f"/costs/{saved['id']}", json={
        **request, "parts": [{**request["parts"][0], "unit_price": "16"}],
    }).json()["data"]["result"]
    assert custom["unit_material"] == "4.00" and custom["bom"][0]["source"] == "用户采购输入"
    missing = owner.post(path + "/costs/calculate", json={
        **request, "tax_included": True, "parts": [{**request["parts"][0], "weight_kg": None}],
    }).json()
    assert missing["partial"] and missing["bom"][0]["raw"] is None
    fallback = owner.post(path + "/costs/calculate", json={
        **request, "parts": [{**request["parts"][0], "material": "PMMA", "process_price": "0", "ai_price_kg": "47"}],
    }).json()
    assert fallback["bom"][0]["source"] == "AI 参考估价"
    results = owner.get(path + "/analysis").json()
    assert len(results["materials"]) == 2 and len(results["costs"]) == 1 and len(results["jobs"]) == 1
    other, _ = add_user(owner, application)
    assert other.get(path + "/analysis").status_code == 404
    assert other.post(path + "/costs/calculate", json=request).status_code == 404
    assert owner.get(f"/api/projects/{project}/export").status_code == 200


def test_xlsx_import_export_and_formula_guard(owner):
    template = owner.get("/api/admin/prices/export?template=true")
    book = load_workbook(io.BytesIO(template.content))
    row = list(price_payload().get(key) for key in ("name", "grade", "spec", "density", "unit_price"))
    row.extend(["kg", "20", "注塑", "1.2", "测试供应商", "供应商正式报价", "2026-01-01", False])
    book.active.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    bulk = {"file": ("pricing.xlsx", buffer.getvalue())}
    result = owner.post("/api/admin/prices/import", files=bulk)
    assert result.status_code == 200, result.text
    assert result.json() == {"created": 1, "updated": 0}
    assert owner.post("/api/admin/prices/import", files=bulk).json() == {"created": 0, "updated": 1}
    assert owner.get("/api/material-prices?q=ABS").json()["items"][0]["unit_price"] == "20"
    output = owner.get("/api/admin/prices/export")
    assert load_workbook(io.BytesIO(output.content)).active["A2"].value == "ABS"
    book.active["E2"] = "=1+1"
    buffer = io.BytesIO()
    book.save(buffer)
    assert owner.post("/api/admin/prices/import", files={"file": ("pricing.xlsx", buffer.getvalue())}).status_code == 422
