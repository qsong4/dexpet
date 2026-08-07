# 阶段一验收清单

- [ ] `./scripts/run.sh` 或分别启动 backend / desktop
- [ ] `GET http://127.0.0.1:8765/health` 返回 `{"status":"ok"}`
- [ ] `./scripts/set_config.sh <api_key>` 配置 DeepSeek（或自定义 base_url/model）
- [ ] 桌面出现透明置顶宠物，可拖拽
- [ ] 发送消息后情绪切到 thinking，流式回复时 speaking，结束后有情绪色变化
- [ ] 请求「一分钟后提醒我喝水」能创建提醒（工具状态可见）
- [ ] API Key 不出现在 `~/Library/Application Support/DexPet/` 明文文件中
- [ ] `pytest -v` 全部通过
