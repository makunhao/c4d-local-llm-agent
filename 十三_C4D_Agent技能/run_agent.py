#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_agent.py —— 用本地 Gemma 4 生成地图数据（C4D Agent 部分）

它做什么
--------
1. 向**本机** Ollama 的 OpenAI 兼容端点发起 function calling，
   让模型自己决定调用 `generate_map_data` 工具
2. 校验模型产出的 JSON（schema / 必填字段 / 坐标是否落在合理范围）
3. 校验失败 → **把错误信息回喂给模型**让它自己修（最多 2 次）
   —— 这一步是 C4D 的核心考点：展示多步推理，
      而不是"模型失败了就由脚本手写一份假数据"

为什么不用 requests / urllib 默认 opener
----------------------------------------
本机设了 http_proxy，urllib 会把发往 127.0.0.1:11434 的请求塞进代理，
代理回一个 502——**本地模型明明在跑却连不上**。
这个坑我在 C2A、C2G 各踩过一次，这里是第三次，直接一开始就绕开。

用法
----
    python run_agent.py --model gemma4:e2b --out map_data.json --pois 6
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

# 郑州西亚斯学院（SIAS University），新郑市。
# 校验半径以内视为"合理"；超出视为模型幻觉 → 回喂让它自修。
CENTER = (34.395, 113.742)          # GCJ-02 近似值
RADIUS_DEG = 0.60                   # 约 60 km，覆盖郑州主城到新郑

TOOLS = [{
    "type": "function",
    "function": {
        "name": "generate_map_data",
        "description": "生成郑州西亚斯学院（SIAS University）周边的地点列表，"
                       "用于渲染交互式地图。",
        "parameters": {
            "type": "object",
            "properties": {
                "pois": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "lat": {"type": "number"},
                            "lng": {"type": "number"},
                            "category": {"type": "string",
                                         "enum": ["campus", "food", "transport",
                                                  "scenic", "shopping", "other"]},
                            "description": {"type": "string"},
                        },
                        "required": ["name", "lat", "lng", "category", "description"],
                    },
                }
            },
            "required": ["pois"],
        },
    },
}]

SYSTEM = ("你是地理信息助手。只输出 JSON。"
          "坐标使用 GCJ-02（火星坐标系），纬度在前、经度在后。"
          "描述用简体中文，每条不超过 40 字。")


def _post(url: str, body: dict, timeout: int = 300) -> dict:
    """★ 绕开环境代理（否则发往 127.0.0.1 的请求会被塞进代理 → 502）。"""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(model: str, messages: list, use_tools: bool, temperature: float = 0.2) -> dict:
    """调一次本地模型。use_tools=True 走 function calling，否则走 JSON 结构化输出。"""
    body: dict = {"model": model, "messages": messages,
                  "temperature": temperature, "stream": False}
    if use_tools:
        body["tools"] = TOOLS
        body["tool_choice"] = "auto"
    else:
        body["response_format"] = {"type": "json_object"}
    return _post("http://127.0.0.1:11434/v1/chat/completions", body)


def validate(data: dict, want: int) -> tuple[bool, list[str]]:
    """schema + 语义校验。返回 (是否合格, 问题列表)。"""
    errs: list[str] = []
    pois = data.get("pois")
    if not isinstance(pois, list):
        return False, [f"缺少 pois 数组（拿到 {type(pois).__name__}）"]
    if len(pois) < want:
        errs.append(f"地点数量不足：要求 ≥{want}，实际 {len(pois)}")
    for i, p in enumerate(pois, 1):
        for k in ("name", "lat", "lng", "category", "description"):
            if k not in p:
                errs.append(f"第 {i} 条缺少字段 {k}")
        try:
            lat, lng = float(p.get("lat", 0)), float(p.get("lng", 0))
        except (TypeError, ValueError):
            errs.append(f"第 {i} 条 lat/lng 不是数字：{p.get('lat')}, {p.get('lng')}")
            continue
        # 坐标必须落在以校区为中心的合理范围（GCJ-02 近似）
        if not (CENTER[0] - RADIUS_DEG < lat < CENTER[0] + RADIUS_DEG):
            errs.append(f"第 {i} 条纬度 {lat} 超出合理范围 "
                        f"({CENTER[0]-RADIUS_DEG:.2f} ~ {CENTER[0]+RADIUS_DEG:.2f})")
        if not (CENTER[1] - RADIUS_DEG < lng < CENTER[1] + RADIUS_DEG):
            errs.append(f"第 {i} 条经度 {lng} 超出合理范围 "
                        f"({CENTER[1]-RADIUS_DEG:.2f} ~ {CENTER[1]+RADIUS_DEG:.2f})")
        if not str(p.get("description", "")).strip():
            errs.append(f"第 {i} 条 description 为空")
    return (len(errs) == 0), errs


def run(model: str, want: int, max_retry: int = 2) -> tuple[dict | None, list]:
    """主循环：生成 → 校验 → 失败回喂。返回 (数据, 过程日志)。"""
    log: list[dict] = []
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user",
                 "content": f"给我生成郑州西亚斯学院（SIAS University）周边的 {want} 个"
                            f"值得标注的地点，调用 generate_map_data 工具。"
                            f"覆盖校园内、餐饮、交通、景点。坐标用 GCJ-02。"}]
    for attempt in range(1, max_retry + 2):
        t0 = time.time()
        try:
            resp = chat(model, messages, use_tools=True)
        except Exception as e:                              # noqa: BLE001
            log.append({"attempt": attempt, "error": f"请求失败 {type(e).__name__}: {e}",
                        "seconds": round(time.time() - t0, 1)})
            return None, log
        secs = round(time.time() - t0, 1)
        msg = resp.get("choices", [{}])[0].get("message", {})
        eval_count = resp.get("eval_count")
        log.append({"attempt": attempt, "seconds": secs,
                    "eval_count": eval_count,
                    "tok_s": round(eval_count / secs, 2) if eval_count and secs else None})

        data = None
        tc = msg.get("tool_calls")
        if tc:                                              # 走了 function calling
            fn = tc[0].get("function", {})
            log.append({"attempt": attempt, "tool_called": fn.get("name")})
            raw = fn.get("arguments", "{}")
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError as e:
                log.append({"attempt": attempt, "json_error": str(e)[:200]})
        if data is None:                                    # 退回普通 JSON 输出
            content = msg.get("content", "")
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}|\[.*\]", content, re.S)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except json.JSONDecodeError:
                        pass
        if data is None:
            log.append({"attempt": attempt, "error": "模型未产出可解析的 JSON"})
            messages.append({"role": "user",
                             "content": "你刚才没有输出合法 JSON。请只输出符合工具参数 schema 的 JSON。"})
            continue

        ok, errs = validate(data, want)
        log.append({"attempt": attempt, "valid": ok, "issues": errs[:8]})
        if ok:
            return data, log
        messages.append({"role": "user",
                         "content": "你生成的数据有以下问题，请修正后重新调用工具：\n- "
                                    + "\n- ".join(errs[:8])})
    return None, log


import re                                                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="本地 Gemma 4 生成地图数据")
    ap.add_argument("--model", default="gemma4:e2b")
    ap.add_argument("--out", default="map_data.json")
    ap.add_argument("--pois", type=int, default=6)
    ap.add_argument("--log", default="agent_run_log.json")
    args = ap.parse_args()

    print(f"[agent] 模型={args.model}  目标地点数={args.pois}")
    print("[agent] 本机 Ollama: 127.0.0.1:11434（CPU 推理）")
    data, log = run(args.model, args.pois)

    Path(args.log).write_text(json.dumps(log, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print("-" * 62)
    for e in log:
        keys = [k for k in ("attempt", "tool_called", "valid", "error",
                            "json_error", "tok_s") if k in e]
        print("  " + "  ".join(f"{k}={e[k]}" for k in keys))
    print("-" * 62)

    if data is None:
        print("✗ 多次重试后仍未拿到合格数据。过程日志 → " + args.log)
        return 1
    n = len(data["pois"])
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"✓ 取得 {n} 个地点 → {args.out}")
    for p in data["pois"]:
        print(f"   {p['lat']:.4f},{p['lng']:.4f}  [{p['category']}]  {p['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
