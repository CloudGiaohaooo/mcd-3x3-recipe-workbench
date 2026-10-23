"""麦当劳 MCP 客户端（纯标准库，无第三方依赖）。

走 Streamable HTTP + JSON-RPC 2.0，Bearer Token 鉴权。
Token 一律从环境变量 MCD_MCP_TOKEN 读取，绝不硬编码 / 写进任何会被提交的文件。

麦当劳 MCP 约定：
- 端点 https://mcp.mcd.cn（protocolVersion 2025-03-26，server "mcd-mcp" v1.0.0）
- 每个 tools/call 的返回都是 result.content[0].text，一段 markdown 说明 + 一段真实 JSON
  真实 JSON 形如 {"success":bool,"code":int,"message":str,"data":...}
  少数工具（list-nutrition-foods）的 data 本身是文本表字符串，需要单独解析。
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, Optional

BASE_URL = "https://mcp.mcd.cn"


class McpError(RuntimeError):
    """MCP 调用失败：网络、鉴权或业务 success=false。"""


def extract_data(content_text: str) -> Dict[str, Any]:
    """从 MCP 返回的 markdown+JSON 文本里，用括号配对取出最后一个顶层 JSON 对象。

    返回形如 {"success":..., "data":...} 的 dict；拿不到就抛 McpError。
    """
    if not content_text:
        raise McpError("MCP 返回空内容")
    i = content_text.rfind('{"success"')
    if i < 0:
        # 少数工具不包 success 字段，退回取最后一个顶层 JSON
        i = content_text.rfind('{"')
        if i < 0:
            raise McpError("MCP 返回里找不到 JSON：%s" % content_text[:120])
    depth = 0
    for j in range(i, len(content_text)):
        c = content_text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(content_text[i:j + 1])
                except json.JSONDecodeError as exc:
                    raise McpError("MCP 返回 JSON 解析失败：%s" % exc)
    raise McpError("MCP 返回 JSON 未闭合")


class McpClient:
    """极简 MCP JSON-RPC 客户端，带内存缓存与超时。"""

    def __init__(self, base_url: str = BASE_URL, token: Optional[str] = None,
                 timeout: float = 30.0):
        self.base_url = base_url
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "")
        self.timeout = timeout
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._id = 0

    @property
    def available(self) -> bool:
        return bool(self.token)

    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base_url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer " + self.token,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise McpError("HTTP %s：%s" % (exc.code, exc.read().decode("utf-8", "replace")[:200]))
        except urllib.error.URLError as exc:
            raise McpError("网络错误：%s" % exc.reason)
        except json.JSONDecodeError as exc:
            raise McpError("MCP 响应非 JSON：%s" % exc)

    def call(self, tool: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """调用一个 MCP 工具，返回业务 data 字典（已含 success/message）。"""
        args = arguments or {}
        if not self.available:
            raise McpError("未设置 MCD_MCP_TOKEN 环境变量，无法调用麦当劳 MCP")
        cache_key = tool + "|" + json.dumps(args, ensure_ascii=False, sort_keys=True)
        if cache_key in self._cache:
            return self._cache[cache_key]
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
        resp = self._post(payload)
        try:
            text = resp["result"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise McpError("MCP 响应结构异常：%s" % json.dumps(resp, ensure_ascii=False)[:200])
        result = extract_data(text)
        if result.get("success") is False:
            raise McpError("MCP 业务失败 %s：%s" % (result.get("code"), result.get("message")))
        self._cache[cache_key] = result
        return result

    # ---- 麦当劳业务工具（统一入参）----

    def nearby_stores(self, city: str, keyword: str, be_type: int = 1) -> Dict[str, Any]:
        """附近门店。searchType=2 需 city+keyword。返回 data[] 里带 storeCode/businessStatus。"""
        return self.call("query-nearby-stores",
                         {"beType": be_type, "searchType": 2, "city": city, "keyword": keyword})

    def menu(self, store_code: str, order_type: int = 1, be_type: int = 1) -> Dict[str, Any]:
        """门店菜单。data={categories:[], meals:{code:{name,currentPrice,...}}}。"""
        return self.call("query-meals",
                         {"storeCode": store_code, "orderType": order_type, "beType": be_type})

    def meal_detail(self, store_code: str, code: str, order_type: int = 1, be_type: int = 1) -> Dict[str, Any]:
        """套餐构成。data={code,name,rounds:[{name,choices:[{code,name,isDefault,diffPrice}]}]}。"""
        return self.call("query-meal-detail",
                         {"storeCode": store_code, "orderType": order_type, "beType": be_type, "code": code})

    def calculate_price(self, store_code: str, items: list, order_type: int = 1, be_type: int = 1) -> Dict[str, Any]:
        """真实计价。items=[{productCode,quantity,couponId?,couponCode?}]；返回单位是「分」。"""
        return self.call("calculate-price",
                         {"storeCode": store_code, "orderType": order_type, "beType": be_type, "items": items})

    def store_coupons(self, store_code: str, order_type: int = 1, be_type: int = 1) -> Dict[str, Any]:
        """门店可用券。data[] 里才有 couponId（title/couponId/couponCode/products/有效期）。"""
        return self.call("query-store-coupons",
                         {"orderType": order_type, "beType": be_type, "storeCode": store_code})

    def nutrition(self) -> Dict[str, Any]:
        """全量营养表。data 是 '[160]{...}\\n 名称,null,kj,kcal,...' 文本，需 parse_nutrition。"""
        return self.call("list-nutrition-foods", {})


def parse_nutrition(data) -> Dict[str, int]:
    """把 list-nutrition-foods 的文本表解析成 {食物名: 千卡}。

    data 形如 '[160]{productName,nutritionDescription,energyKj,energyKcal,protein,...}:\n  中薯条,null,1210,289,...\n...'
    """
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, str):
        return {}
    out: Dict[str, int] = {}
    for line in data.splitlines():
        line = line.strip()
        if not line or line.startswith("[") or line.startswith("{"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        name, kcal = parts[0], parts[3]
        if kcal in ("", "null") or not kcal.lstrip("-").isdigit():
            continue
        out[name] = int(kcal)
    return out


def cents_to_yuan(v) -> float:
    """calculate-price 返回单位是分；转元（保留 1 位）。"""
    try:
        return round(float(v) / 100.0, 1)
    except (TypeError, ValueError):
        return 0.0
