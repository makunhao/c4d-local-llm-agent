# C4D · 教学说明

> 作者：十三　｜　挑战：C4D 本地大模型 Agent 技能（Gemma 4）
> 目标读者：想在自己电脑上跑通"本地模型 + 交互式地图"的人

---

## 一、30 秒看懂整个流程

```
本地 Gemma 4（Ollama）
   ↓ ①函数调用：模型自己决定调用 generate_map_data
校验器（schema + 坐标范围）
   ↓ ②不合格就把错误喂回模型，让它自己修（最多 2 次）
map_data.json
   ↓ ③渲染
map.html（腾讯地图，可缩放/可点标记）
```

**第 ② 步是 C4D 的考点**：不是"模型给什么就用什么"，也不是"模型失败就脚本兜底"，
而是**让模型在反馈中自我修正**。

---

## 二、环境准备

### 2.1 你需要什么

| 项 | 最低要求 | 说明 |
|---|---|---|
| Ollama | 任意近期版本 | 从 ollama.com 下载安装包 |
| 磁盘 | ≥ 8 GB 空闲 | Gemma 4 E2B 约 5–6 GB |
| 内存 | ≥ 8 GB | CPU 推理即可，**不需要 GPU** |
| Python | ≥ 3.9 | 只用标准库，**零第三方依赖** |

### 2.2 下载模型

```bash
ollama pull gemma4:e2b     # 四款里最小，CPU/老机器现实之选
```

> **怎么确认下载完成**：`ollama list` 能看到 `gemma4:e2b` 就行。
> 我第一次拉到 987MB 时卡死了（13 分钟不动），
> 处理办法是杀掉进程重新 `pull`——Ollama 支持断点续传，不用从头下。

### 2.3 确认服务在跑

```bash
curl http://127.0.0.1:11434/api/tags
# 应返回一个 JSON，里面有你的模型列表
```

> ⚠️ **如果你本机设了 http_proxy**，这一步可能返回 502——
> 不是模型坏了，是请求被代理劫持了。详见第五节。

---

## 三、跑 Agent

```bash
# ① 让本地模型生成地点数据（含校验与自修正）
python 十三_C4D_Agent技能/run_agent.py --model gemma4:e2b --out map_data.json --pois 6

# ② 渲染成交互式地图
python 十三_C4D_Agent技能/build_map.py map_data.json --out map.html --model gemma4:e2b

# ③ 浏览器打开 map.html：可缩放、可点击标记看详情
```

**第 ① 步的输出长这样**（每次会略有不同，模型有随机性）：

```text
[agent] 模型=gemma4:e2b  目标地点数=6
[agent] 本机 Ollama: 127.0.0.1:11434（CPU 推理）
------------------------------------------------------------
  attempt=1  tool_called=generate_map_data
  attempt=1  valid=False  issues=[第 3 条纬度 45.2 超出合理范围 …]
  attempt=2  tool_called=generate_map_data
  attempt=2  valid=True   issues=[]
------------------------------------------------------------
✓ 取得 6 个地点 → map_data.json
```

**看到 `valid=False` 不要慌**——那正是 Agent 在自我修正，
过程会完整记录在 `十三_C4D_Agent技能/agent_run_log.json` 里。

---

## 四、怎么验证"真的在本地跑"

挑战要求截图里必须能看到四样东西。我的做法：

| 要求 | 怎么满足 |
|---|---|
| 模型名称与版本 | `ollama list` 输出（`gemma4:e2b`） |
| 运行工具 | `ollama --version` |
| 设备信息 | `systeminfo` 摘要（CPU/内存/无 GPU） |
| 推理速度 tok/s | `十三_C4D_Agent技能/agent_run_log.json` 里的 `tok_s` 字段（来自 Ollama 返回的 `eval_count`） |

这些都来自**真实运行日志**，不是我手抄的。

---

## 五、常见问题（都是我真踩过的）

### Q1：本地模型明明在跑，程序却报 502 / 连不上

**这是代理劫持**。如果你的环境设了 `http_proxy`/`https_proxy`，
Python 的 urllib 会把发往 `127.0.0.1:11434` 的请求塞进代理。

本技能的 `run_agent.py` 已经内置绕开（`build_opener(ProxyHandler({}))`）。
如果你自己写脚本，**记住：连本机服务必须绕代理**。
我在 C2A、C2G 各踩过一次，这里是第三次。

### Q2：模型生成的坐标偏得离谱

两种可能：
- **坐标系不对**：腾讯地图要 GCJ-02（火星坐标），模型给的可能偏 WGS-84。校验器已留出余量
- **就是幻觉**：2B 模型的地理知识有限。校验器会把超范围的坐标**回喂给模型**让它重修

### Q3：地图一片空白 / 灰色

- 检查容器有没有**固定高度**（`height: 100vh`），flex 布局下尤其容易漏
- **不要传 `mapStyleId`**——自定义样式需要单独在腾讯位置服务控制台激活，默认密钥不支持
- 不要在设了 `_TMapSecurityConfig` 之后再调 `TMap.setConfig()`，两者一起用会白屏

### Q4：为什么不用 Leaflet？

Leaflet 默认搭配 OpenStreetMap（境外瓦片源），在境内渲染境内地图有合规与可用性风险。
本技能改用**腾讯地图 GL JS**（合规白名单内），并用它的 key 代理模式——
**前端代码里没有任何密钥**。详见《拿来说明》第二节。

### Q5：CPU 推理很慢？

正常。E2B 在纯 CPU 上生成几百 token 需要几十秒到几分钟。
`十三_C4D_Agent技能/agent_run_log.json` 里的 `tok_s` 会告诉你实际速度——**是多少写多少，不要美化**。

---

## 六、改造成你自己的 Agent

`run_agent.py` 的骨架是通用的，换任务只需要改两处：

1. `TOOLS`：换成你自己的工具 schema（比如"生成旅行计划""生成试卷"）
2. `validate()`：换成你这个任务的校验规则

**校验 + 回喂这个模式保留**——它是这个 Agent 真正"有能力"的部分。
