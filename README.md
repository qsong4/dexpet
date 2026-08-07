# DexPet

macOS 桌面智能宠物助手 — 阶段一 MVP。

## 功能

- 透明置顶可拖拽宠物窗 + 精灵帧动画
- 可选 Live2D 渲染（用户自备模型；未安装依赖或加载失败时回退精灵帧）
- OpenAI Chat Completions 兼容对话（默认 DeepSeek，可自定义端点）
- 情感状态机驱动语气与动画
- 自然语言提醒（宠物气泡弹出）
- 会话/配置本地 SQLite；API Key 存 Keychain

## 要求

- macOS
- Python 3.11+

## 安装

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# 可选 Live2D（macOS arm64 等有 wheel）：
# pip install -e ".[live2d]"
```

国内网络较慢时，可用中科大镜像：

```bash
pip install -e ".[dev]" \
  -i https://pypi.mirrors.ustc.edu.cn/simple/ \
  --trusted-host pypi.mirrors.ustc.edu.cn
```

或写入当前环境持久配置：

```bash
pip config set global.index-url https://pypi.mirrors.ustc.edu.cn/simple/
pip config set global.trusted-host pypi.mirrors.ustc.edu.cn
```

## 配置 LLM

浏览器打开后台配置页：

```text
http://127.0.0.1:8765/settings
```

或右键桌面猫咪 →「打开设置…」。

也可以用脚本：

| 字段 | 说明 | DeepSeek 示例 |
| :--- | :--- | :--- |
| `base_url` | API 根地址 | `https://api.deepseek.com` |
| `model` | 模型 ID | `deepseek-chat` |
| `api_key` | 密钥（写入 Keychain） | `sk-...` |

自定义任意 OpenAI 兼容端点时，填入对应的 `base_url`、`model`、`api_key` 即可。

```bash
curl -X PUT http://127.0.0.1:8765/config \
  -H 'Content-Type: application/json' \
  -d '{"provider_preset":"deepseek","base_url":"https://api.deepseek.com","model":"deepseek-chat","api_key":"sk-xxx"}'
```

## 启动

分别启动：

```bash
source .venv/bin/activate
dexpet-backend   # 或: python -m backend.main
dexpet-desktop   # 或: python -m desktop.main
```

一键启动：

```bash
./scripts/run.sh
# 或
python dexpet_app.py
```

## 打包为 macOS .app

使用 PyInstaller（`packaging/DexPet.spec` + `scripts/build_app.sh`）。应用图标为 `desktop/assets/AppIcon.icns`（源图 `desktop/assets/app_icon.png`），默认打成精灵帧可运行的 `.app`，**不捆绑** Live2D 模型。

```bash
./scripts/build_app.sh
open dist/DexPet.app
```

产物在 `dist/DexPet.app`。双击即可启动（会自动拉起本地后端）。首次对话前仍需配置 API Key：

```bash
./scripts/set_config.sh sk-your-key
```

未签名时，若 Gatekeeper 拦截，可在「系统设置 → 隐私与安全性」中允许，或执行：

```bash
xattr -cr dist/DexPet.app
```

配置 API Key（backend 需已启动）：

```bash
./scripts/set_config.sh sk-your-key
# 自定义兼容端点：
./scripts/set_config.sh sk-your-key https://api.openai.com/v1 gpt-4o-mini custom
```

## Live2D（可选）

1. `pip install -e ".[live2d]"`
2. 自备已授权模型目录（含 `.model3.json` 或 `.model.json`），**不要**把未授权模型或 Cubism 密钥提交进仓库
3. 设置页 →「宠物」→ 形象引擎选 Live2D，填写模型路径并保存

详见 [desktop/assets/live2d/README.md](desktop/assets/live2d/README.md) 与 [docs/plans/2026-08-06-live2d-support.md](docs/plans/2026-08-06-live2d-support.md)。

## 验收

见 [docs/plans/2026-08-05-mvp-acceptance.md](docs/plans/2026-08-05-mvp-acceptance.md)。

## 测试

```bash
pytest -v
```

## 提醒

到期后会在桌面猫咪上方弹出聊天气泡（需保持 DexPet 桌面端与后端运行）。
