# MobileFlow AI

轻量级、LLM 驱动的移动端自动化框架。用自然语言描述任务，LLM 决策，Appium 执行；内置记忆/RAG、失败自愈、断言、用例生成等工程化能力。**零重型依赖**，保持"轻框架、LLM 原生决策"定位。

- **规模**：约 3000 行核心代码 · **193 用例 · 84% 覆盖率** · 核心代码 ruff 零告警
- **模型无关**：商汤 GLM-5.2 / agnes-2.5-pro / deepseek / 商汤 flash-lite 随换（环境变量切换）

## 架构

```
用户指令（自然语言）
   ↓
决策链：稳定记忆链回放 → RAG 语义召回 → 技能库匹配 → LLM 在线决策
   ↓ JSON 动作
Appium 封装层（click/input/swipe/back/scroll/open_app/视觉点击/断言）
   ↓ WebDriver 协议
设备（Android/iOS 模拟器/真机/云真机）
   ↑ 观察回传
UI 树(page source XML)→压缩文本→LLM      ← 主通道（纯文本可决策）
截图→多模态模型描述/结构化坐标            ← 视觉通道（--vision，可选，支持纯视觉点击）
```

## 项目结构

```
mobileflow/          核心包
  agent.py           主决策循环：记忆/RAG/技能/LLM + 失败自愈接入
  driver.py          Appium 封装：幂等/非幂等策略、坐标/视觉点击、断言路由
  llm.py             LlmClient：模型无关，OpenAI 兼容接口
  vision.py          视觉通道：要点描述 + 结构化坐标 + 纯视觉点击
  memory.py          记忆引擎：精确哈希 + 纯 numpy 字符 n-gram RAG
  planner.py         长任务规划：持久 Agent + 步骤提取 + 回滚
  recoverer.py       失败自愈：截屏→视觉→LLM 重规划
  skills.py          技能库：YAML 加载/注册/描述匹配
  assertion.py       断言系统：元素/视觉/性能(内存)/网络
  testdata.py        测试数据工厂：边界值/参数化/生成器/数据表
  usecase.py         LLM 用例生成：自然语言 → 技能 YAML
  report.py          报告产出：summary.json + Allure 兼容
  config.py          启动配置校验
  wait_strategy.py   等待策略：显式/智能等待 + 重试
  cli.py             命令行入口
tools/               GLM-5.2 生成 + agnes 评审的质量闭环脚本
tests/               193 用例
```

## 核心能力

| 能力 | 说明 |
|---|---|
| 三层决策链 | 稳定记忆链（快）> RAG 语义召回（泛化）> 技能库（准）> LLM 在线（通用） |
| 失败自愈 | 动作失败自动截屏→视觉分析→LLM 重规划→重试验证，而非僵化重试 |
| 纯视觉点击 | 无 UI 树时用模型识别元素坐标直接点击 |
| 断言系统 | 元素存在/视觉可见/内存/网络 四类，统一 AssertionFailed |
| 测试数据工厂 | `Boundaries` 边界值、`Parametrize` 笛卡尔积、`Factory` 生成器 |
| LLM 用例生成 | 一句话需求 → 校验 → 技能 YAML |
| 工程化报告 | `--report dir` 产出 summary.json + Allure 结构 |
| 启动校验 | 缺 key/路径不可写等配错在启动时拦截（exit 2，零 token） |

## 设计要点

- **GLM-5.2 无视觉不是问题**：Appium page source 是 XML 文本，压缩后直接给文本模型理解；视觉作为可选增强通道
- **商汤渠道约束适配**：`reasoning_effort=none` 直出；流式生成（`tools/gen_code.py`）绕开 max_tokens 配额；大输出分块防 429
- **RAG 零新依赖**：纯 numpy 字符 n-gram + TF-IDF + 余弦，对中文天然有效

## 快速开始

```bash
# 1. 装依赖（本框架自带 venv 环境用 uv）
uv pip install --python /opt/hermes/.venv/bin/python3 -e .

# 2. 配置模型（商汤 GLM-5.2 示例）
export MOBILEFLOW_BASE_URL=https://token.sensenova.cn/v1
export MOBILEFLOW_API_KEY=sk-xxx
export MOBILEFLOW_MODEL=glm-5.2

# 3. 起 Appium 服务
appium --base-path /wd/hub

# 4. 跑任务
mobileflow run "打开微信，给文件传输助手发一条'你好'"     # 真实设备
mobileflow run "打开微信" --dry-run                       # 无设备验证决策链路
mobileflow run "打开设置" --vision --trace /tmp/trace.jsonl   # 视觉+轨迹
mobileflow run "..." --report ./report                    # 工程化报告

# 5. 技能/记忆管理
mobileflow skills list
mobileflow skills add my_skill.yaml
mobileflow memory          # 记忆/RAG 统计
```

## 环境变量

| 变量 | 用途 | 示例/默认 |
|---|---|---|
| `MOBILEFLOW_BASE_URL` | LLM 端点（OpenAI 兼容） | `https://token.sensenova.cn/v1` |
| `MOBILEFLOW_API_KEY` | LLM 密钥 | `sk-xxx` |
| `MOBILEFLOW_MODEL` | LLM 模型名 | `glm-5.2` |
| `MOBILEFLOW_VISION_API_KEY` | 视觉通道密钥（Agnes） | 缺则回退 `AGNES_API_KEY` / `.env` |
| `MOBILEFLOW_VISION_MODEL` | 视觉模型 | `agnes-2.5-pro` |
| `MOBILEFLOW_ENV_FILE` | 凭证 .env 路径 | 默认 `/opt/data/.env` |

## 动作协议（LLM 输出的 JSON）

```json
{"action": "click", "target": {"text": "发送"}}
{"action": "click", "target": {"resource_id": "com.tencent.mm:id/..."}}
{"action": "click", "target": {"index": 3}}
{"action": "input", "target": {"text": "..."}, "text": "你好"}
{"action": "swipe", "start": [500, 1500], "end": [500, 500]}
{"action": "scroll", "direction": "down"}
{"action": "back"} / {"action": "home"}
{"action": "open_app", "package": "com.tencent.mm"}
{"action": "done", "summary": "任务完成说明"}
```

## 断言（YAML 步骤可用）

```yaml
- action: assert_exists        # 元素存在
  target: {text: 发送}
- action: assert_visible       # 视觉可见（严格片段匹配，防"买"误中"购买按钮"）
  name: 购买按钮
- action: assert_memory        # 内存 < 500MB
  max_mb: 500
- action: assert_network       # 网络在线
  online: true
```

## 测试 / 开发

```bash
pytest                       # 193 用例
pytest --cov=mobileflow      # 覆盖率
ruff check mobileflow        # lint（核心代码零告警）
```

## 质量闭环（开发工具）

```
tools/gen_code.py    GLM-5.2 流式生成代码（stream 绕开商汤配额）
tools/review_code.py agnes 交叉评审（--gate 可做 CI 质量闸门）
```

流程：GLM-5.2 生成 → agnes 评审 → 修复 → 复评。多轮实测抓到断言误命中、私有方法耦合、路径穿越等真问题。

## 路线图

- [x] MVP：LLM 决策 + Appium 封装 + Agent 循环
- [x] 质量闭环：GLM-5.2 生成 ↔ agnes 评审
- [x] 视觉通道 / 记忆链 / 技能库 / 轨迹审计
- [x] RAG 语义召回（纯 numpy）
- [x] 失败自愈 / 纯视觉坐标点击
- [x] 断言系统 / 测试数据工厂 / LLM 用例生成
- [x] 工程化报告 / 启动配置校验 / lint 全清
- [ ] 真实设备验证（Appium + 真机）
- [ ] 安全门禁（高危确认 + 脱敏）
- [ ] iOS (XCUITest) 支持
- [ ] CI 加模拟器冒烟