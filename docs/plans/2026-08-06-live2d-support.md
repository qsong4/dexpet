# Live2D Support — Design & Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 DexPet 桌面宠物可选使用用户自备的 Live2D 模型渲染，未安装依赖或加载失败时无缝回退现有精灵帧。

**Architecture:** 在 `desktop/` 引入可替换的宠物渲染器（`SpriteAnimator` | `Live2DPetWidget`），统一 `set_emotion` / `set_facing` 接口；设置存 SQLite `pet_state`，经 `/pet` 与 WS `pet_settings` 同步。Live2D 为可选依赖（`live2d-py`），不捆绑 Cubism 密钥或商业模型。

**Tech Stack:** PySide6 `QOpenGLWidget`、`live2d-py`（Cubism Native 封装）、FastAPI `/pet`、现有透明置顶窗。

---

## 1. 背景与调研

### 1.1 现状渲染管线

| 组件 | 职责 |
| :--- | :--- |
| `desktop/window.py` `PetWindow` | 透明置顶窗；布局底部放 `self.sprite`；气泡绝对定位；拖拽/漫游/WS |
| `desktop/sprite_animator.py` | `QWidget` + `paintEvent`；情绪调色/自定义 PNG；`set_emotion` / `set_facing` |
| `desktop/wander.py` | 走动时调用 `window.sprite.set_facing` |
| `/sprites` API + 设置页 | 按情绪上传帧图 |

架构文档曾写「Live2D 暂缓，`PetRenderer` 可替换」——本功能兑现该扩展点。

### 1.2 方案对比

| 方案 | 优点 | 缺点 | 结论 |
| :--- | :--- | :--- | :--- |
| **A. live2d-py + QOpenGLWidget** | 官方示例含 PySide6；macOS arm64 wheel；Cubism 2/3；与现有 Qt 一体 | 需 OpenGL；透明嵌套窗偶发平台差异；v3 依赖 Cubism Core（wheel 已打入第三方封装，源码构建需自备 SDK） | **采用** |
| B. Cubism Web SDK + QWebEngine | 文档多 | 体积大、透明/置顶差、与精灵布局难统一 | 否 |
| C. 自绑 Cubism Native | 可控 | 授权文件、构建链、维护成本过高 | 否（后续若商业发布再评估） |

### 1.3 授权与分发约束

- **不提交 / 不捆绑** Live2D Cubism 商业密钥、SDK 源码包、未授权模型。
- `live2d-py` 为第三方封装（MIT）；其预编译 wheel 含运行时；**源码编译**需从 [Live2D 官网](https://www.live2d.com/en/sdk/download/native/) 自行下载 Cubism Core/Framework 并同意其协议。
- **发布许可**：使用 Cubism SDK 发布内容时，个体/小规模主体通常有豁免，但「可扩展应用」（如通用 Avatar 平台）需单独审查——DexPet 桌宠属嵌入式展示，开源分发时 README 须标明用户自备模型与自行遵守 Live2D 协议。
- **模型**：用户自备（官方 Sample / 自行购买授权）；仓库仅放放置说明。

### 1.4 阻塞点（已知）

1. **无模型时无法演示真实 Live2D 画面**——CI/开发机无授权模型则只能测配置与回退。
2. **macOS 透明 `QOpenGLWidget` 作为子控件**：多数情况可用 `clearBuffer` + `WA_TranslucentBackground`；若黑底，后续可改为顶层 GL 窗或 FBO 贴图到 `QWidget`。
3. **商业 `.app` 打包分发**：若捆绑 `live2d-py`/Cubism Runtime，发布前需复核 Live2D Publication License；MVP 默认不把 Live2D 打进必选依赖。

---

## 2. 设计

### 2.1 渲染器协议

两者均暴露：

- `set_emotion(state: str)`
- `set_facing(facing: int)`  # 1 / -1
- `_state: str`（兼容现有 `PetWindow` 状态判断）
- 固定约 180×180，透明背景

`PetWindow.sprite` 继续指向当前渲染器（命名保留，减少 wander/bubble 改动）。

### 2.2 配置

`pet_state` 键：

| Key | 值 | 默认 |
| :--- | :--- | :--- |
| `renderer` | `sprite` \| `live2d` | `sprite` |
| `live2d_model_path` | 模型目录或 `*.model3.json` / `*.model.json` 绝对路径 | `""` |

`GET/PUT /pet` 扩展字段；变更经 WS `pet_settings` 广播，桌面热切换（失败则回退 sprite 并上报 `live2d_error`）。

### 2.3 加载与回退

1. `renderer != live2d` → `SpriteAnimator`
2. 未安装 `live2d-py` → sprite + `live2d_available: false`
3. 路径无效 / 无 model json / `LoadModelJson` 失败 → sprite + 错误信息写入响应/状态
4. 成功 → `Live2DPetWidget`

模型路径解析：文件则直接用；目录则递归/浅层查找首个 `*.model3.json`，否则 `*.model.json`。

### 2.4 情绪映射（尽力）

1. `GetExpressionIds()` 别名匹配（happy→Smile 等）
2. 否则 `StartRandomMotion`（Idle / TapBody 等常见组）
3. 否则微调 `StandardParams`（嘴角、眉等）
4. 无可用能力则仅保持 idle 呼吸（SDK 自动 blink/breath）

### 2.5 交互兼容

- 拖拽/右键/气泡/漫游逻辑不变；GL 控件不拦截父窗拖拽（鼠标事件忽略或透传）。
- 漫游 `set_facing` → Live2D `SetScaleX(±1)` 或等价。

### 2.6 可选依赖

```toml
[project.optional-dependencies]
live2d = ["live2d-py>=0.7.0"]
```

安装：`pip install -e ".[live2d]"`（或 `.[dev,live2d]`）。

---

## 3. 实现任务

### Task 1: 纯逻辑 — 可用性与路径解析

**Files:**
- Create: `desktop/live2d_runtime.py`
- Test: `tests/test_live2d_config.py`

函数：`live2d_importable()`、`resolve_model_json(path)`、`normalize_renderer()`、情绪别名表。

### Task 2: Live2D Widget + Factory

**Files:**
- Create: `desktop/live2d_widget.py`
- Create: `desktop/pet_factory.py`
- Modify: `desktop/window.py`（创建/热切换 `self.sprite`）

### Task 3: Backend + 设置页

**Files:**
- Modify: `shared/messages.py` `PetSettingsUpdate`
- Modify: `backend/api/http.py` `/pet`
- Modify: `backend/api/settings_page.py`（渲染模式 + 路径 + 说明）

### Task 4: 文档与依赖

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `desktop/assets/live2d/README.md`

### Task 5: 测试

- API 读写 `renderer` / `live2d_model_path`
- 无效路径解析失败
- `live2d_importable` 在无包时为 False（可 mock）
- 可选：`import live2d.v3` 冒烟（有依赖则 skip 或 pass）

---

## 4. 非目标（MVP 不做）

- 口型同步 / TTS 联动
- 面捕
- 捆绑官方 Sample 模型
- Windows 优先适配（接口保持跨平台，验证以 macOS 为准）
- 打包脚本强制打入 live2d-py
