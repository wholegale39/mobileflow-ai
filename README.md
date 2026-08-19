# MobileFlow AI

Appium 封装的 LLM 驱动移动端自动化框架。用自然语言描述任务，GLM-5.2 决策，Appium 执行。

## 架构

```
用户指令（自然语言）
   ↓
决策层 GLM-5.2（tools 调用，输出 JSON 动作）
   ↓
Appium 封装层（click/input/swipe/back/scroll/断言适配器）
   ↓ WebDriver 协议
设备（Android/iOS 模拟器/真机/云真机）
   ↑
观察回传：page source(UI树XML)→压缩文本→GLM-5.2（纯文本理解界面）
           截图→多模态模型（可选增强）
```

## 设计要点

- **GLM-5.2 无视觉不是问题**：Appium page source 是 XML 文本，压缩后直接给文本模型理解
- **商汤渠道约束适配**：`reasoning_effort=none` 直出；max_tokens 控制在 300 内（动作 JSON 很短）；单轮单请求 + 节流
- **模型无关**：LlmClient 是 OpenAI 兼容接口，换任何模型改配置即可

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

# 4. 跑任务（需设备/模拟器，或 --dry-run 只验证决策）
mobileflow run "打开微信，给文件传输助手发一条'你好'"
```

## 动作协议（GLM-5.2 输出的 JSON）

```json
{"action": "click", "target": {"text": "发送"}}
{"action": "input", "target": {"resource_id": "com.tencent.mm:id/...", "text": "你好"}}
{"action": "swipe", "start": [500, 1500], "end": [500, 500]}
{"action": "back"}
{"action": "home"}
{"action": "open_app", "package": "com.tencent.mm"}
{"action": "done", "summary": "任务完成说明"}
```

## 路线图

- [x] MVP 骨架：LLM 决策 + Appium 封装 + Agent 循环 + CLI
- [ ] UI 树压缩优化（去噪/分块）
- [ ] 记忆链 + 断言验证
- [ ] 截图多模态通道
- [ ] iOS (XCUITest) 支持
- [ ] CI（GitHub Actions + Android 模拟器）
