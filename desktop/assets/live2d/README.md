# Live2D 模型放置说明

DexPet **不捆绑** Live2D 商业密钥或模型。请使用你已获得授权的模型（例如 Live2D 官方 Sample，或你自行购买/制作的模型）。

## 1. 安装可选依赖

```bash
source .venv/bin/activate
pip install -e ".[live2d]"
```

需要：Python 3.11+、macOS arm64 推荐；依赖包为第三方 `live2d-py`（含 Cubism 运行时封装）。

## 2. 准备模型目录

典型 Cubism 3+ 目录结构：

```text
MyModel/
  MyModel.model3.json
  MyModel.moc3
  MyModel.physics3.json
  textures/
    texture_00.png
  motions/   # 可选
  expressions/  # 可选
```

Cubism 2 则为 `*.model.json` + `*.moc`。

可将整个目录放在任意本机路径，例如：

```text
~/Library/Application Support/DexPet/live2d/MyModel/
```

（本仓库的 `desktop/assets/live2d/` 仅作说明，**不含模型文件**；有商用/署名限制的模型也不要 commit 进 git。）

### 推荐：官方免费猫模型 Tororo & Hijiki

真猫示例（白猫 Tororo / 黑猫 Hijiki），Live2D 官方 Sample Data：

- 页面：https://www.live2d.com/en/learn/sample/tororo-hijiki/
- 许可：须同意 [Free Material License Agreement](https://www.live2d.com/eula/live2d-free-material-license-agreement_en.html) 与 [Sample Data Terms of Use](https://www.live2d.com/eula/live2d-sample-model-terms_en.html)（Live2D Original Characters）
- 商用：个人 / 小规模企业（年营业额 &lt; 1000 万日元）通常可商用与非商用；中大规模企业有额外限制；公开发布需按条款标注版权声明
- 建议本机路径（勿入库）：

```text
~/Library/Application Support/DexPet/live2d/tororo_hijiki/tororo/runtime/
# 或黑猫：
~/Library/Application Support/DexPet/live2d/tororo_hijiki/hijiki/runtime/
```

下载 zip：`https://cubism.live2d.com/sample-data/bin/tororo_hijiki/tororo_hijiki_ja.zip`  
解压后填上述 `runtime` 目录（内含 `*.model3.json`）。

## 3. 在设置里切换

1. 打开 http://127.0.0.1:8765/settings →「宠物」
2. 形象引擎选 **Live2D**
3. 模型路径填目录，或直接填 `…/MyModel.model3.json`
4. 保存；桌宠会热切换。失败时自动回退精灵帧。

## 4. 授权提醒

- 使用 Cubism SDK / 运行时发布作品时，请自行遵守 [Live2D 许可](https://www.live2d.com/en/sdk/license/)。
- 勿将未授权模型或 Cubism 密钥提交到本仓库。
- 官方 Sample 使用时请自行阅读并遵守其素材许可与版权声明要求。