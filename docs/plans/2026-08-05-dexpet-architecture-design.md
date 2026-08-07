# DexPet 架构设计（修订版）

**文档版本**：1.1  
**编写日期**：2026-08-05  
**项目名称**：macOS 桌面智能宠物助手（DexPet）

## 1. 目标

构建运行于 macOS 的桌面宠物助手：可交互角色、OpenAI Chat Completions 兼容大模型对话、插件化能力扩展、短期会话记忆与情感状态联动。

## 2. 设计原则

- 模块化与可扩展（插件）
- 跨模型兼容（统一 OpenAI 兼容客户端）
- 本地优先（数据与 Key 本地存储）
- MVP 先行，后续增强

## 3. 修订结论（相对初版）

| 原方案 | 修订后 |
| :--- | :--- |
| Live2D | 精灵帧默认；可选 Live2D（见 `2026-08-06-live2d-support.md`） |
| vLLM / Ollama 本地 | 不内置本地推理；通用 OpenAI 兼容端点 |
| 多厂商 SDK | 单一 `OpenAICompatibleClient`（`base_url` + `model` + `api_key`） |
| 情感状态机后期 | MVP 纳入核心 |
| 双进程 HTTP/WS | 保留：PySide6 + FastAPI WebSocket |

默认预设：DeepSeek（`https://api.deepseek.com` / `deepseek-chat`）。

## 4. 分层架构

1. **表现层**（`desktop/`）：透明置顶窗、精灵动画、输入/气泡、WS 客户端  
2. **智能核心**（`backend/core/`）：对话管理、情感状态机、LLM、工具路由  
3. **能力扩展**（`backend/plugins/`）：提醒等插件  
4. **持久化**（`backend/db/` + Keychain）：SQLite、API Key

## 5. 进程与通信

- Backend：FastAPI，`ws://127.0.0.1:8765/ws`，HTTP `/health` `/config`
- Desktop：PySide6，连接后流式收发 JSON 消息
- 消息类型：`user_message` / `token` / `emotion_changed` / `tool_status` / `error` / `ping` / `pong`

## 6. 情感状态机

状态：`idle` | `happy` | `curious` | `thinking` | `speaking` | `sad` | `surprised`  
驱动：交互事件 + 回复情绪标注 + 关键词兜底  
副作用：system prompt 语气、动画、SQLite `pet_state`

## 7. 数据

路径：`~/Library/Application Support/DexPet/`  
表：`sessions` / `messages` / `reminders` / `pet_state` / `settings`  
敏感信息：macOS Keychain（`dexpet` service）

## 8. MVP 范围

包含：双进程骨架、精灵动画、流式对话、情感机、提醒插件、SQLite + Keychain  
暂缓：ChromaDB、TTS（Live2D / 股票 / 系统插件 / `.app` 打包已另案推进）

## 9. 阶段路线

1. MVP（本文实现）  
2. 配置 UI、历史摘要、长期记忆（SQLite FTS）  
3. 股票/系统控制插件  
4. TTS、打包分发
