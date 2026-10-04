# C4D · 本地大模型 Agent 技能 —— 交付包索引

> 作者：十三　｜　挑战：C4D 本地大模型 Agent 技能（Gemma 4）
> **最后更新：2026-10-04**
> 一句话：**在本机 CPU 上跑通 Gemma 4 E2B，Agent 通过函数调用生成地点数据，
> 校验失败后模型自我修正，最终渲染成合规的腾讯地图交互式 HTML。**

---

## 〇、最硬的三条证据

| # | 证据 | 数字 |
|---|---|---|
| 1 | **本地模型真实运行** | `gemma4:e2b`（4.6 GB，ID b37049369adf）+ Ollama 0.31.1 + 纯 CPU（无独立 GPU） |
| 2 | **推理速度实测** | **37.55 tok/s**（`eval_count=469` / `eval_duration=12.49s`，来自 Ollama 原生 `/api/chat`） |
| 3 | **Agent 多步推理** | 2 轮：第 1 轮 6 条坐标全部越界被判无效 → 回喂错误 → 第 2 轮模型自修正通过 |

---

## 一、交付物对照表

| 挑战要求的文件 | 本包文件 | 状态 |
|---|---|---|
| `姓名_C4D_方案设计.md` | **`十三_C4D_方案设计.md`** | ✅ |
| `姓名_C4D_Agent技能/` | **`十三_C4D_Agent技能/`**（`run_agent.py` + `build_map.py` + 运行产物） | ✅ |
| `姓名_C4D_demo/`（含 map.html 与截图） | **`十三_C4D_demo/`**（`十三_C4D_map.html` + `十三_C4D_output_screenshots/`） | ✅ 6 标记点，可缩放/可点击 |
| `姓名_C4D_AAR.md`（必须） | **`十三_C4D_AAR.md`** | ✅ 七维课后复盘 |
| `姓名_C4D_验证报告.md` | **`十三_C4D_验证报告.md`** | ✅ |
| `姓名_C4D_教学说明.md` | **`十三_C4D_教学说明.md`** | ✅ |
| `姓名_C4D_AI日志.md`（必须） | **`十三_C4D_AI日志.md`** | ✅ |
| `姓名_C4D_拿来说明.md` | **`十三_C4D_拿来说明.md`** | ✅ |

---

## 二、Agent 能力（对应"Agent 能力展示 25%"）

```
用户指令："给我生成一个 SIAS University 周边的地图"
        ↓
① 函数调用：模型自己决定调用 generate_map_data
        ↓
② 结构化输出：严格符合 schema 的 JSON（name/lat/lng/category/description）
        ↓
③ 校验：schema + 必填字段 + 坐标落在校区合理半径内
        ↓ 第 1 轮失败（6 条经度越界）→ 把错误清单回喂给模型
④ 模型自我修正 → 第 2 轮通过
        ↓
⑤ 渲染：腾讯地图 GL JS，多标记点 + 点击信息窗
```

**实跑日志**（`十三_C4D_Agent技能/agent_run_log.json`）：

```text
attempt=1  tool_called=generate_map_data
attempt=1  valid=false  issues=[第1条经度110.3超出范围…×6]
attempt=2  tool_called=generate_map_data
attempt=2  valid=true   issues=[]
```

> **第 1 轮的失败不是坏事，是证据**：它证明校验器在工作，
> 也证明了模型能在收到具体错误后自我修正。
> 详见《验证报告》第三节——**包括"修正 ≠ 正确"这个诚实边界**。

---

## 三、一处主动的技术替换（详见《拿来说明》）

| 挑战建议 | 我用的 | 为什么 |
|---|---|---|
| Leaflet.js / Folium（默认配 OpenStreetMap） | **腾讯地图 GL JS（key 代理模式）** | OSM 是境外瓦片源，境内渲染有合规与可用性风险；且"数据主权"正是 C4D 的主题——**前端代码里没有任何密钥** |

---

## 四、复现

```bash
# ① 模型（~4.6 GB）
ollama pull gemma4:e2b

# ② Agent 生成数据（含校验与自修正，零第三方库）
python 十三_C4D_Agent技能/run_agent.py --model gemma4:e2b --out map_data.json --pois 6

# ③ 渲染地图
python 十三_C4D_Agent技能/build_map.py map_data.json --out map.html --model gemma4:e2b

# ④ 浏览器打开 map.html
```

依赖：Python ≥ 3.9，**零第三方库**。

> ⚠️ 两个常见坑（都写进了《教学说明》）：
> ① 本机设了 `http_proxy` 时，直接用 urllib 会把发往 `127.0.0.1` 的请求塞进代理 → 502；
> ② Ollama 的 `partial` 文件是**预分配**的，大小恒定，**下载进度要看 mtime 而不是 size**
> ——我把一个健康的下载当卡死杀掉了，浪费 30 分钟。

---

## 五、目录结构

```
C4D交付包/
├── README.md                        ← 本文件
├── 十三_C4D_方案设计.md
├── 十三_C4D_验证报告.md
├── 十三_C4D_教学说明.md
├── 十三_C4D_AI日志.md
├── 十三_C4D_拿来说明.md
├── 十三_C4D_AAR.md                  ← 课后复盘（七维）
├── 十三_C4D_Agent技能/
│   ├── run_agent.py                 ← ★ Agent 主程序（函数调用 + 校验回喂）
│   ├── build_map.py                 ← 地图渲染器（合规模板）
│   ├── map_data.json                ← 模型实际产出的数据
│   └── agent_run_log.json           ← ★ Agent 运行过程日志（含 2 轮校验记录）
└── 十三_C4D_demo/
    ├── 十三_C4D_map.html            ← 交互式地图（腾讯地图，6 标记点）
    └── 十三_C4D_output_screenshots/
        └── 运行环境证据.json          ← ★ 模型名/Ollama版本/设备/tok/s
```

---

## 六、已知不能通过的项目（诚实清单）

| 项 | 状态 | 说明 |
|---|---|---|
| GPU 推理 | ❌ | 本机无独立 NVIDIA GPU |
| 多设备 / 多量化对比 | ❌ | 只有一台机器、一种量化 |
| Uncensored 模型对比 | ❌ | 未下载 |
| **标记点地理准确性** | ⚠️ | 模型坐标**系统性偏移**（认为校区在东经 110.4°，实际 113.7°）；校验回喂拉回合理区间，**但不等于准确** |
| 浏览器截图 | ⚠️ | 地图瓦片需在能替换代理占位符的环境里打开；运行证据以 JSON + 日志形式提供 |
