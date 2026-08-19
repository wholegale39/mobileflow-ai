# MobileFlow AI

Appium 封装的 LLM 驱动移动端自动化框架。自然语言描述任务，LLM 决策，Appium 执行。**模型完全可配置**（GLM-5.2 / agnes-2.5-pro / deepseek / 商汤 flash-lite 随换）。

## 架构

```
用户指令（自然语言）
   ↓
决策链：稳定记忆链回放 → 技能库匹配 → LLM 在线决策
   ↓ JSON 动作
Appium 封装层（click/input/swipe/back/scroll/open_app/断言适配器）
   ↓ WebDriver 协议
设备（Android/iOS 模拟器/真机/云真机）
   ↑ 观察回传
UI 树(page source XML)→压缩文本→LLM      ← 主通道（纯文本可决策）
截图→多模态模型描述→补充决策             ← 视觉通道（--vision 可选）
轨迹审计 JSONL                           ← 可观测性
```

## 设计要点

- **GLM-5.2 无视觉不是问题**：Appium page source 是 XML 文本，压缩后直接给文本模型理解；视觉作为可选增强通道
- **模型无关**：`MOBILEFLOW_BASE_URL/API_KEY/MODEL` 环境变量切换，运行时零改动
- **三层决策链**：稳定记忆链（快）> 技能库（准）> LLM 在线（通用），层层兜底
- **商汤渠道约束适配**：`reasoning_effort=none` 直出；流式生成（`tools/gen_code.py`）绕开 max_tokens 配额

## 快速开始

```bash
# 1. 装依赖
uv pip install --python /opt/hermes/.venv/bin/python3 -e .

# 2. 配置模型（商汤 GLM-5.2 示例）
export MOBILEFLOW_BASE_URL=https://token.sensenova.cn/v1
export MOBILEFLOW_API_KEY=sk-xxx
export MOBILEFLOW_MODEL=glm-5.2

# 3. 起 Appium 服务
appium --base-path /wd/hub

# 4. 跑任务
mobileflow run "打开微信，给文件传输助手发一条'你好'"          # 真实设备
mobileflow run "打开微信" --dry-run                            # 无设备验证决策链路
mobileflow run "打开设置" --vision --trace /tmp/trace.jsonl    # 视觉通道+轨迹审计

# 5. 技能/记忆管理
mobileflow skills list
mobileflow skills add my_skill.yaml
mobileflow memory          # 记忆统计
```

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

## 质量闭环（开发工具）

```
tools/gen_code.py    GLM-5.2 流式生成代码（stream 绕开商汤配额）
tools/review_code.py agnes-2.5-pro 交叉评审（--gate 可做 CI 质量闸门）
```

流程：GLM-5.2 生成 → agnes-2.5-pro 评审 → 修复 → 复评。已实测评审抓到停滞检测未实现等 2 个严重问题。

## 未来演进方向（结合行业趋势设计）

移动端 Agent 正从「无障碍+截图 hack」走向「系统级 UI 语义 + 混合推理」。工程为此预留：

| 趋势（2026-2028） | 本工程设计 |
|---|---|
| **UI 语义化**：坐标/选择器 → 语义 UI 树 → 系统级 View Hierarchy / App Intents | 语义适配层：UI 树源可切换（当前 Appium XML，未来系统 API / 云真机流） |
| **混合推理**：端侧小模型 + 云旗舰，按任务路由 | LlmClient 模型无关 + 决策链分层（记忆/技能/LLM）；预留模型路由配置 |
| **技能标准化**：任务技能对齐 MCP mobile 协议 | 技能库 YAML 格式（name/description/steps/params），可导出标准协议 |
| **可观测性**：Agent 轨迹审计、调试、合规 | 轨迹 JSONL（`--trace`），未来对接 agent-tracer 类工具 |
| **安全门禁**：高危操作确认、敏感信息脱敏 | 计划中：高危动作（支付/发送/删除）确认弹窗 + 截图脱敏 |
| **确定性执行 + 智能理解分离** | Appium 保证确定性，LLM 只做理解/规划（架构已固化） |

## 路线图

- [x] MVP：LLM 决策 + Appium 封装 + Agent 循环 + 44 测试
- [x] 质量闭环：GLM-5.2 生成 ↔ agnes-2.5-pro 评审
- [x] V2：视觉通道 / 记忆链 / 技能库 / 轨迹审计
- [ ] 真实设备验证（Appium + 模拟器/真机）
- [ ] 安全门禁（高危确认 + 脱敏）
- [ ] iOS (XCUITest) 支持
- [ ] CI 加 Android 模拟器冒烟
