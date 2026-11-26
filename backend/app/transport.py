import asyncio
import ipaddress
import os
import re
import socket
from pathlib import Path

import httpx
from cryptography.fernet import Fernet, InvalidToken

from app.core import fail

OFFICIAL = {"openai": "https://api.openai.com/v1", "gemini": "https://generativelanguage.googleapis.com/v1beta"}
MAX_RESPONSE = 80 * 1024 * 1024
IPV6_TRANSLATION = (ipaddress.ip_network("64:ff9b::/96"), ipaddress.ip_network("64:ff9b:1::/48"))


class UpstreamError(Exception):
    def __init__(self, message: str, *, status: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.request_id = request_id


def fixed_endpoint(protocol: str) -> str | None:
    return OFFICIAL.get(protocol)


def public_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped or ip.sixtofour or ip.teredo or any(ip in net for net in IPV6_TRANSLATION):
            return False
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified or ip.is_link_local)


def check_url(value: str) -> httpx.URL:
    try:
        url = httpx.URL(value)
        host = url.raw_host.decode("ascii")
        if url.scheme != "https" or not host or url.port not in {None, 443} or url.userinfo or url.fragment:
            raise ValueError
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or host.endswith((".local", ".localhost", ".internal", ".home", ".lan", ".")):
                raise ValueError from None
        else:
            if not public_ip(str(ip)):
                raise ValueError
        return url
    except (ValueError, UnicodeError, httpx.InvalidURL) as error:
        raise UpstreamError("连接地址必须为公网 HTTPS，且不含凭据、片段或自定义端口") from error


def normalize_endpoint(value: str) -> str:
    try:
        url = check_url(value)
        if url.query or not re.fullmatch(r"(?:/[A-Za-z0-9_.~-]+)*/?", url.path) or any(
            part in {".", ".."} for part in url.path.split("/")
        ):
            raise UpstreamError("Base URL 请填写完整 HTTPS 接口前缀，不含查询参数")
    except UpstreamError as error:
        fail(422, str(error))
    return str(url).rstrip("/")


def vault(directory: Path, *, create: bool = True) -> Fernet:
    filename = directory / "provider.key"
    if create and not filename.is_file():
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        try:
            descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as file:
                file.write(Fernet.generate_key())
                file.flush()
                os.fsync(file.fileno())
    try:
        return Fernet(filename.read_bytes().strip())
    except (OSError, ValueError) as error:
        raise UpstreamError("无法读取实例密钥，请检查独立密钥卷") from error


def seal(directory: Path, key: str) -> str:
    try:
        return vault(directory).encrypt(key.encode()).decode("ascii")
    except UpstreamError as error:
        fail(503, str(error))


def unseal(directory: Path, token: str | None) -> str:
    if not token:
        raise UpstreamError("该服务商缺少 API Key")
    try:
        return vault(directory, create=False).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as error:
        raise UpstreamError("API Key 无法解密，请恢复密钥卷或重新录入") from error


async def pinned_address(url: httpx.URL) -> str:
    entries = await asyncio.get_running_loop().getaddrinfo(url.host, 443, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(entry[4][0] for entry in entries))
    if not addresses or any(not public_ip(address) for address in addresses):
        raise UpstreamError("目标域名未解析为可访问的公网地址")
    return next((address for address in addresses if ":" not in address), addresses[0])


def response_id(headers: httpx.Headers) -> str | None:
    value = headers.get("x-request-id") or headers.get("x-goog-request-id")
    return value if value and re.fullmatch(r"[A-Za-z0-9:_-]{1,120}", value) else None


class SafeHTTP:
    """Use the address checked during this request, while preserving TLS host verification."""

    def __init__(self, timeout: int):
        self.timeout = timeout

    async def request(self, method, destination, *, headers=None, limit=MAX_RESPONSE, **body):
        url = check_url(destination)
        remote_id = None
        try:
            async with asyncio.timeout(self.timeout):
                address = await pinned_address(url)
                request_headers = {**(headers or {}), "Host": url.netloc.decode(), "Accept-Encoding": "identity"}
                async with httpx.AsyncClient(
                    trust_env=False, follow_redirects=False, timeout=self.timeout,
                ) as client, client.stream(
                    method, url.copy_with(host=address), headers=request_headers,
                    extensions={"sni_hostname": url.host}, **body,
                ) as response:
                    remote_id = response_id(response.headers)
                    if not response.is_success:
                        code = response.status_code
                        reason = {
                            400: "请求参数、图片格式或所选模型能力不匹配", 401: "API Key 未获授权",
                            403: "服务商拒绝访问该资源", 404: "接口或模型不存在", 413: "上游输入体积超限",
                            422: "服务商拒绝处理所选输入", 429: "达到服务商配额或速率限制",
                        }.get(code, "上游请求失败")
                        raise UpstreamError(f"{reason}（HTTP {code}）", status=code, request_id=remote_id)
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise UpstreamError("上游响应使用了未支持的传输压缩")
                    output = bytearray()
                    async for part in response.aiter_raw():
                        if len(output) + len(part) > limit:
                            raise UpstreamError("上游响应超出大小限制")
                        output.extend(part)
                    return bytes(output), response.status_code, remote_id
        except (TimeoutError, httpx.TimeoutException) as error:
            raise UpstreamError("上游超时。服务商可能已接收请求。", request_id=remote_id) from error
        except (httpx.RequestError, OSError) as error:
            raise UpstreamError("无法连接服务商，请检查 DNS、TLS 或网络", request_id=remote_id) from error
