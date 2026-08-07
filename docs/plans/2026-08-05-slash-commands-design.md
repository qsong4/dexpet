# Slash Commands Design

**Goal:** 聊天输入支持 `/` 内置命令，不走 LLM。

**Architecture:** 后端 WebSocket 在 `user_message` 入口检测以 `/` 开头的文本，交给 `SlashCommandHandler` 处理，用现有 `token`/`done` 回气泡。命令不写入对话历史。

## Commands

| Command | Behavior |
|---------|----------|
| `/list` | 列出 pending 提醒 |
| `/clear` | 清空当前会话消息与摘要 |
| `/help` | 列出可用命令 |
| unknown | 提示未知命令 |

## Notes

- 斜杠命令不依赖 API Key（可在未配置时使用）
- 桌面端无需改发送协议
