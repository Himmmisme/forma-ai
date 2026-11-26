import base64
import hashlib
import io
import json
import re
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageOps

from app.storage import OUTPUT_LIMIT
from app.transport import SafeHTTP, UpstreamError

VX_BASE_URL = "https://la-api.vxvxvx.top/v1"
VX_IMAGE_MODES = {
    "gpt-image-2.5": "text_to_image",
    "gpt-image-2.5-pro": "text_to_image",
    "gemini-nano-banana-2.1": "single_image",
    "gemini-3-pro-image-preview": "single_image",
    "gemini-3.1-flash-image-preview": "single_image",
}
VX_IMAGE_SIZES = {"1K", "2K", "4K", "1024x1024"}
IMAGE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def vx_image_mode(base_url: str, model: str) -> str | None:
    return VX_IMAGE_MODES.get(model) if base_url == VX_BASE_URL else None


@dataclass(frozen=True)
class ImageInput:
    mime: str
    data: bytes

    @property
    def encoded(self):
        return base64.b64encode(self.data).decode("ascii")

    @property
    def uri(self):
        return f"data:{self.mime};base64,{self.encoded}"


def numeric_usage(value, depth=0):
    if not isinstance(value, dict) or depth >= 3:
        return None
    return {
        key: numeric_usage(item, depth + 1) if isinstance(item, dict) else item
        for key, item in list(value.items())[:32]
        if len(key) <= 48 and (isinstance(item, dict) or isinstance(item, int) and 0 <= item < 10**12)
    }


def decoded_image(value):
    if not isinstance(value, str) or len(value) > 4 * (OUTPUT_LIMIT // 3 + 1):
        raise UpstreamError("服务商图片数据无效或超过大小限制")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as error:
        raise UpstreamError("服务商图片 Base64 无效") from error


def check_vx_image_response(response, http_status):
    error = response.get("error")
    reason = response.get("failure_reason")
    if error or reason or response.get("status") == "failed":
        for detail in (error.get("message") if isinstance(error, dict) else error, reason):
            if isinstance(detail, str) and (match := re.search(r"\bstatus_code=([45][0-9]{2})\b", detail[:1024])):
                raise UpstreamError(f"VX API 报告上游 HTTP {match[1]}，请查看对应的 VX 使用日志")
        raise UpstreamError(f"VX API 在 HTTP {http_status} 响应中报告生图失败，请查看对应的 VX 使用日志")
    if response.get("status", "succeeded") != "succeeded":
        raise UpstreamError("VX API 未返回生图成功的终态，请查看对应的 VX 使用日志")
    rows = response.get("data")
    if not isinstance(rows, list) or not any(
        isinstance(row, dict) and any(isinstance(row.get(key), str) and row[key] for key in ("url", "b64_json"))
        for row in rows
    ):
        raise UpstreamError("VX API 响应缺少可下载的图片链接或 Base64 数据")


class RemoteAdapter:
    def __init__(self, base_url, key, timeout, observer, http=None):
        self.base_url = base_url
        self.key = key
        self.http = http or SafeHTTP(timeout)
        self.observer = observer

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.key}"}

    async def json(self, operation, path, *, method="POST", vx_image=False, **kwargs):
        log = self.observer.start(operation)
        status = request_id = None
        try:
            raw, status, request_id = await self.http.request(method, self.base_url + path, headers=self.headers, **kwargs)
            response = json.loads(raw)
            if not isinstance(response, dict):
                raise UpstreamError("服务商返回了错误或无效响应")
            if vx_image:
                check_vx_image_response(response, status)
            elif response.get("error"):
                raise UpstreamError("服务商返回了错误或无效响应")
        except (ValueError, UnicodeError) as error:
            self.observer.finish(log, "failed", status, request_id)
            raise UpstreamError("服务商返回了无效 JSON") from error
        except UpstreamError as error:
            self.observer.finish(log, "failed", error.status or status, error.request_id or request_id)
            raise
        self.observer.finish(log, "succeeded", status, request_id,
                             numeric_usage(response.get("usage") or response.get("usageMetadata")))
        return response

    async def connect(self):
        result = await self.json("models.list", "/models", method="GET", limit=2 * 1024 * 1024)
        rows = result.get("data", result.get("models"))
        if not isinstance(rows, list):
            raise UpstreamError("服务商未返回模型列表")
        return {"message": "连接成功", "models": [str(row.get("id") or row.get("name"))[:120]
                                                for row in rows[:40] if isinstance(row, dict)]}


class OpenAIAdapter(RemoteAdapter):
    async def text(self, model, prompt, images):
        content = [{"type": "input_text", "text": prompt}]
        content.extend({"type": "input_image", "image_url": image.uri} for image in images)
        data = await self.json("responses", "/responses", json={
            "model": model, "input": [{"role": "user", "content": content}], "store": False,
        })
        return "\n".join(part["text"] for row in data["output"] if row.get("type") == "message"
                         for part in row["content"] if part.get("type") == "output_text")

    async def images(self, model, prompt, images, output):
        fields = {"model": model, "prompt": prompt, "size": output["size"], "n": str(output["count"])}
        if images:
            files = [("image[]", (f"input-{index}.{IMAGE_EXTENSIONS[image.mime]}", image.data, image.mime))
                     for index, image in enumerate(images)]
            data = await self.json("images.edits", "/images/edits", data=fields, files=files)
        else:
            data = await self.json("images.generations", "/images/generations", json={**fields, "n": output["count"]})
        return await self.image_results(data, output["count"])

    async def image_results(self, data, count):
        files = []
        for row in data["data"][:count + 1]:
            if row.get("b64_json"):
                files.append(decoded_image(row["b64_json"]))
            elif isinstance(row.get("url"), str):
                # Signed asset URL is separately checked with no provider credentials.
                raw, _, _ = await self.http.request("GET", row["url"], limit=OUTPUT_LIMIT)
                files.append(raw)
        return files


class CompatibleAdapter(OpenAIAdapter):
    async def text(self, model, prompt, images):
        content = [{"type": "text", "text": prompt}]
        content.extend({"type": "image_url", "image_url": {"url": image.uri}} for image in images)
        data = await self.json("chat.completions", "/chat/completions", json={
            "model": model, "messages": [{"role": "user", "content": content if images else prompt}],
        })
        return data["choices"][0]["message"]["content"]

    async def images(self, model, prompt, images, output):
        mode = vx_image_mode(self.base_url, model)
        if not mode:
            return await super().images(model, prompt, images, output)
        if mode == "text_to_image" and images:
            raise UpstreamError("VX API 的该型号仅有文生图接口。请为原图生成选择支持图片编辑的型号")
        if len(images) > 1 or output["count"] != 1:
            raise UpstreamError("VX API 的该型号每次最多接收一张输入图并生成一张结果图")
        size = output["size"]
        if size not in VX_IMAGE_SIZES:
            raise UpstreamError("VX API 图片规格请填写 1K、2K 或 4K")
        fields = {"model": model, "prompt": prompt, "size": "1K" if size == "1024x1024" else size,
                  "aspect_ratio": output["ratio"]}
        if images:
            image = images[0]
            content = image.data
            if image.mime != "image/png":
                buffer = io.BytesIO()
                with Image.open(io.BytesIO(content)) as decoded:
                    decoded.save(buffer, "PNG")
                content = buffer.getvalue()
            files = [("image", ("input.png", content, "image/png"))]
            data = await self.json("images.edits", "/images/edits", vx_image=True,
                                   data={**fields, "n": "1", "stream": "false"}, files=files)
        else:
            if mode == "text_to_image":
                if len(prompt) > 1024 or output["ratio"] not in {"1:1", "3:2", "2:3"}:
                    raise UpstreamError("VX API 的该型号要求提示词最多 1024 字，比例为 1:1、3:2 或 2:3")
                fields.update({"quality": "auto", "async": False})
            else:
                fields["n"] = 1
            data = await self.json("images.generations", "/images/generations", vx_image=True,
                                   json={**fields, "stream": False})
        return await self.image_results(data, 1)


class GeminiAdapter(RemoteAdapter):
    @property
    def headers(self):
        return {"x-goog-api-key": self.key}

    async def content(self, model, prompt, images, config=None):
        parts = [{"text": prompt}]
        parts.extend({"inlineData": {"mimeType": image.mime, "data": image.encoded}} for image in images)
        body = {"contents": [{"role": "user", "parts": parts}]}
        if config:
            body["generationConfig"] = config
        response = await self.json("generateContent", f"/models/{model}:generateContent", json=body)
        return [part for item in response.get("candidates", []) for part in item.get("content", {}).get("parts", [])
                if not part.get("thought")]

    async def text(self, model, prompt, images):
        return "\n".join(part["text"] for part in await self.content(model, prompt, images) if "text" in part)

    async def images(self, model, prompt, images, output):
        image_config = {"aspectRatio": output["ratio"]}
        if output["size"] != "default":
            image_config["imageSize"] = output["size"]
        config = {"responseModalities": ["IMAGE"], "imageConfig": image_config}
        results = []
        for _ in range(output["count"]):
            for part in await self.content(model, prompt, images, config):
                item = part.get("inlineData") or part.get("inline_data")
                if item:
                    results.append(decoded_image(item.get("data")))
                    break
            else:
                raise UpstreamError("Gemini 未返回图片，请检查模型输出模态、使用限制或内容过滤")
        return results


ADAPTERS = {"openai": OpenAIAdapter, "gemini": GeminiAdapter, "compatible": CompatibleAdapter}


def mock_images(images: list[ImageInput], output: dict, prompt: str):
    background = {"studio": "#e5e9e1", "white": "#ffffff", "dark": "#202a24", "context": "#bdc7b6"}
    width, height = map(int, output["size"].split("x"))
    source = Image.open(io.BytesIO(images[0].data)).convert("RGB")
    fitted = ImageOps.contain(source, (round(width * .94), round(height * .94)))
    hues = hashlib.sha256(prompt.encode()).digest()
    results = []
    for index in range(output["count"]):
        tint = tuple(70 + channel % 144 for channel in hues[3 * index:3 * index + 3])
        styled = ImageEnhance.Contrast(Image.blend(fitted, Image.new("RGB", fitted.size, tint), .18)).enhance(1.14)
        canvas = Image.new("RGB", (width, height), background[output["background"]])
        canvas.paste(styled, ((width - styled.width) // 2, (height - styled.height) // 2))
        data = io.BytesIO()
        canvas.save(data, "PNG", optimize=False)
        results.append(data.getvalue())
    return results


def structured(text: str) -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 80_000:
        raise UpstreamError("服务商未返回可用文本或返回体过长")
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        value = json.loads(text)
    except ValueError as error:
        raise UpstreamError("AI 文本未符合约定 JSON 输出") from error
    if not isinstance(value, dict):
        raise UpstreamError("AI 文本必须返回结构化对象")
    return value
