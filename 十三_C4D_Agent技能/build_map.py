#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_map.py —— 把模型生成的地点数据渲染成交互式地图（C4D）

★ 合规说明（重要，也是对挑战建议的技术选型的一处替换）
--------------------------------------------------------
挑战原文建议 Leaflet.js / Folium。**Leaflet 的默认瓦片源是 OpenStreetMap，
属于境外瓦片服务**，在中国境内使用有两类风险：
  · 合规风险：境内互联网地图服务对资质有明确要求
  · 可用性风险：境外瓦片加载不稳定
因此这里改用**腾讯地图 GL JS**（合规白名单内），并采用它的
**key 代理模式**：前端代码里不出现任何密钥，密钥由本地代理持有。

坐标系：GCJ-02（火星坐标）。
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

CENTER = (34.395, 113.742)          # 郑州西亚斯学院（GCJ-02 近似）

CATEGORY_ICON = {
    "campus":    "🏫",
    "food":      "🍜",
    "transport": "🚌",
    "scenic":    "🌳",
    "shopping":  "🛍️",
    "other":     "📍",
}

# 占位符**原样保留**（WorkBuddy 运行时会替换），不要填成具体值
TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SIAS University 周边地图（本地 Gemma 4 生成）</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%; }
  #map { width: 100%; height: 100vh; }
  #info { position: absolute; left: 12px; top: 12px; z-index: 1000;
          background: rgba(255,255,255,.94); padding: 10px 14px;
          border-radius: 8px; font: 13px/1.6 -apple-system, "PingFang SC",
          "Microsoft YaHei", sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,.15); }
  #info b { color: #d97706; }
</style>
<script type="text/javascript">
    window._TMapSecurityConfig = {
        serviceHost: 'http://127.0.0.1:__WB_HTTP_PORT__/_TMapService/_wbt/__WB_TMAP_SECRET__',
    };
</script>
<script src="https://map.qq.com/api/gljs?v=1.exp"></script>
</head>
<body>
<div id="map"></div>
<div id="info"><b>__TITLE__</b><br>__SUBTITLE__<br>
地点数据由本地模型 __MODEL__ 生成（GCJ-02）</div>
<script>
  const map = new TMap.Map('map', {
    zoom: 13,
    center: new TMap.LatLng(__CLAT__, __CLNG__),
  });
  const pois = __POIS_JSON__;
  const styles = {
    default: new TMap.MarkerStyle({
      width: 26, height: 34,
      anchor: { x: 13, y: 34 },
      color: '#d97706',
    }),
  };
  const geoms = pois.map((p, i) => ({
    id: String(i),
    styleId: 'default',
    position: new TMap.LatLng(p.lat, p.lng),
    properties: p,
  }));
  const markers = new TMap.MultiMarker({ map, styles, geometries: geoms });

  const info = new TMap.InfoWindow({ map, position: map.getCenter(), offset: { x: 0, y: -36 } });
  markers.on('click', (evt) => {
    const p = evt.geometry.properties;
    const icon = __ICON_MAP__;
    info.open();
    info.setPosition(evt.latLng);
    info.setContent(
      '<div style="font:14px/1.7 -apple-system,\'PingFang SC\',sans-serif;min-width:200px">'
      + '<div style="font-weight:700;margin-bottom:4px">' + (icon[p.category] || '📍') + ' '
      + p.name + '</div>'
      + '<div style="color:#666">[' + p.category + ']</div>'
      + '<div style="color:#333">' + p.description + '</div>'
      + '<div style="color:#999;font-size:12px;margin-top:4px">'
      + p.lat.toFixed(5) + ', ' + p.lng.toFixed(5) + '</div></div>');
  });
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="地点 JSON → 腾讯地图交互式 HTML")
    ap.add_argument("data", help="run_agent.py 产出的 map_data.json")
    ap.add_argument("--out", default="map.html")
    ap.add_argument("--model", default="gemma4:e2b")
    args = ap.parse_args()

    src = Path(args.data)
    if not src.exists():
        sys.exit(f"找不到数据文件：{src}（先跑 run_agent.py）")
    data = json.loads(src.read_text(encoding="utf-8"))
    pois = data.get("pois", [])
    if not pois:
        sys.exit("pois 为空——模型没有产出有效数据， refusing to render an empty map")

    # 转义所有进入 HTML 的模型输出（模型输出是不可信输入）
    safe = [{**p, "name": html.escape(str(p["name"])),
             "description": html.escape(str(p["description"])),
             "category": html.escape(str(p["category"]))} for p in pois]

    icon_map = json.dumps(CATEGORY_ICON, ensure_ascii=False)
    out = (TPL
           .replace("__TITLE__", html.escape("郑州西亚斯学院 · 周边地点"))
           .replace("__SUBTITLE__",
                    html.escape(f"共 {len(pois)} 个标记点，可缩放、可点击查看详情"))
           .replace("__MODEL__", html.escape(args.model))
           .replace("__CLAT__", f"{CENTER[0]}")
           .replace("__CLNG__", f"{CENTER[1]}")
           .replace("__POIS_JSON__", json.dumps(safe, ensure_ascii=False, indent=2))
           .replace("__ICON_MAP__", icon_map))

    Path(args.out).write_text(out, encoding="utf-8")
    print("=" * 62)
    print(f"地图生成 · {len(pois)} 个标记点 → {args.out}")
    print("-" * 62)
    for p in pois:
        icon = CATEGORY_ICON.get(p.get("category", "other"), "📍")
        print(f"  {icon} {p['name']:<20} {p['lat']:.4f},{p['lng']:.4f}")
    print("-" * 62)
    print("地图源：腾讯地图 GL JS（合规白名单内，key 由本地代理持有）")
    print("坐标系：GCJ-02")
    print("在浏览器打开即可交互（缩放 / 点击标记看详情）")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
