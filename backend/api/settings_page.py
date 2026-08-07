"""Static settings page HTML for DexPet admin UI."""

SETTINGS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>DexPet 设置</title>
  <style>
    :root {
      --bg: #f3ebe1;
      --card: #fffaf4;
      --ink: #2a221c;
      --muted: #7a6a5a;
      --accent: #d4892e;
      --line: rgba(42, 34, 28, 0.12);
      --ok: #2f7d4a;
      --err: #b33a3a;
      --panel: #f7efe4;
      --nav: #fff8f0;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; min-height: 100vh;
      font-family: "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(1000px 500px at 10% -10%, #ffe7c2 0%, transparent 55%),
        radial-gradient(800px 400px at 100% 0%, #f0d6ff 0%, transparent 50%),
        var(--bg);
    }
    .shell {
      width: min(960px, calc(100% - 24px));
      margin: 32px auto 48px;
      display: grid;
      grid-template-columns: 200px 1fr;
      gap: 16px;
      align-items: start;
    }
    @media (max-width: 720px) {
      .shell { grid-template-columns: 1fr; }
      .nav { position: sticky; top: 0; z-index: 5; display: flex; flex-wrap: wrap; gap: 6px; }
      .nav button { flex: 1 1 auto; }
    }
    .nav {
      background: var(--nav);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      box-shadow: 0 10px 28px rgba(60, 40, 20, 0.06);
    }
    .nav .brand { font-weight: 700; font-size: 1.05rem; margin: 0 0 4px; }
    .nav .hint { color: var(--muted); font-size: 0.78rem; margin: 0 0 12px; }
    .nav button {
      width: 100%; text-align: left; border: 0; background: transparent;
      border-radius: 12px; padding: 10px 12px; margin-bottom: 4px;
      cursor: pointer; color: var(--ink); font-size: 0.92rem;
    }
    .nav button:hover { background: rgba(212,137,46,.1); }
    .nav button.active {
      background: rgba(212,137,46,.18);
      color: #8a5310; font-weight: 650;
    }
    main {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 24px 26px 28px;
      box-shadow: 0 18px 40px rgba(60, 40, 20, 0.08);
      min-height: 520px;
    }
    .panel { display: none; }
    .panel.active { display: block; }
    h1 { margin: 0 0 6px; font-size: 1.45rem; }
    h2 { margin: 0 0 8px; font-size: 1.05rem; }
    .sub { margin: 0 0 18px; color: var(--muted); font-size: 0.92rem; line-height: 1.45; }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      background: rgba(212, 137, 46, 0.12); color: var(--accent);
      font-size: 0.72rem; margin-left: 8px; vertical-align: middle;
    }
    .switch-panel, .current, .block {
      background: var(--panel); border: 1px solid var(--line);
      border-radius: 16px; padding: 16px; margin-bottom: 14px;
    }
    .switch-title, .block-title {
      font-size: 0.82rem; color: var(--muted); margin-bottom: 10px; font-weight: 600;
    }
    .api-switch { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .api-card {
      text-align: left; border: 1.5px solid var(--line); background: #fff;
      border-radius: 14px; padding: 14px 14px 12px; cursor: pointer;
    }
    .api-card:hover { border-color: rgba(212,137,46,.45); }
    .api-card.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(212,137,46,.18);
    }
    .api-card .name { font-weight: 650; margin-bottom: 6px; display: flex; justify-content: space-between; }
    .api-card .meta { font-size: 0.8rem; color: var(--muted); word-break: break-all; line-height: 1.45; white-space: pre-line; }
    .api-card .tag {
      font-size: 0.7rem; font-weight: 600; padding: 2px 8px; border-radius: 999px;
      background: rgba(47,125,74,.12); color: var(--ok);
    }
    .api-card:not(.active) .tag { display: none; }
    .pill {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 2px 10px; border-radius: 999px; font-size: 0.75rem;
      background: rgba(47, 125, 74, 0.12); color: var(--ok);
    }
    .pill.off { background: rgba(179, 58, 58, 0.1); color: var(--err); }
    .pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    .current dl {
      margin: 0; display: grid; grid-template-columns: 88px 1fr;
      gap: 8px 12px; align-items: baseline;
    }
    .current dt { color: var(--muted); font-size: 0.82rem; }
    .current dd { margin: 0; font-size: 0.95rem; word-break: break-all; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .current .model-name { font-size: 1.1rem; font-weight: 650; font-family: inherit; }
    .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 4px; }
    button { border: 0; border-radius: 999px; padding: 10px 16px; font-size: 0.92rem; cursor: pointer; }
    .primary { background: var(--accent); color: #fff; }
    .ghost { background: #fff; color: var(--muted); border: 1px solid var(--line); }
    .danger { background: rgba(179,58,58,.1); color: var(--err); border: 1px solid rgba(179,58,58,.2); }
    .status { font-size: 0.88rem; min-height: 1.2em; }
    .status.ok { color: var(--ok); }
    .status.err { color: var(--err); }
    .toggle-row {
      display: flex; align-items: center; justify-content: space-between; gap: 12px;
      background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px;
    }
    .toggle-row .label { font-weight: 600; }
    .toggle-row .desc { color: var(--muted); font-size: 0.82rem; margin-top: 4px; }
    .switch {
      position: relative; width: 46px; height: 26px; flex: 0 0 auto;
    }
    .switch input { opacity: 0; width: 0; height: 0; }
    .switch span {
      position: absolute; inset: 0; border-radius: 999px; background: #d7c8b8;
      cursor: pointer; transition: .15s;
    }
    .switch span::before {
      content: ""; position: absolute; width: 20px; height: 20px; left: 3px; top: 3px;
      border-radius: 50%; background: #fff; transition: .15s;
    }
    .switch input:checked + span { background: var(--accent); }
    .switch input:checked + span::before { transform: translateX(20px); }
    .sprite-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 12px; margin-top: 12px;
    }
    .sprite-card {
      background: #fff; border: 1px solid var(--line);
      border-radius: 14px; padding: 12px; text-align: center;
    }
    .sprite-card .label { font-size: 0.82rem; color: var(--muted); margin-bottom: 8px; }
    .sprite-preview {
      width: 88px; height: 88px; margin: 0 auto 10px; border-radius: 16px;
      background: var(--panel); border: 1px dashed var(--line);
      display: flex; align-items: center; justify-content: center; overflow: hidden;
    }
    .sprite-preview img { width: 100%; height: 100%; object-fit: contain; }
    .sprite-preview .empty { font-size: 0.72rem; color: var(--muted); padding: 6px; }
    .sprite-actions { display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
    .sprite-actions button { padding: 6px 10px; font-size: 0.78rem; }
    table.whitelist {
      width: 100%; border-collapse: collapse; background: #fff;
      border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
    }
    table.whitelist th, table.whitelist td {
      padding: 10px 12px; border-bottom: 1px solid var(--line);
      text-align: left; font-size: 0.9rem;
    }
    table.whitelist th { background: var(--panel); color: var(--muted); font-weight: 600; font-size: 0.8rem; }
    table.whitelist tr:last-child td { border-bottom: 0; }
    table.whitelist .app-name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }
    table.whitelist button { padding: 6px 10px; font-size: 0.78rem; }
    .add-row {
      display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; margin-top: 12px;
    }
    .model-list { display: flex; flex-direction: column; gap: 10px; }
    .model-row {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 12px;
      align-items: center;
      background: var(--panel);
      border: 1.5px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
    }
    .model-row.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(212,137,46,.16);
      background: #fff;
    }
    .model-row .radio {
      width: 18px; height: 18px; accent-color: var(--accent);
    }
    .model-row .title { font-weight: 650; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }
    .model-row .meta { font-size: 0.8rem; color: var(--muted); line-height: 1.45; word-break: break-all; }
    .model-row .meta code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.78rem;
    }
    .model-row .actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
    .model-row .actions button { padding: 7px 12px; font-size: 0.8rem; }
    @media (max-width: 560px) {
      .api-switch, .add-row, .row { grid-template-columns: 1fr; }
      .model-row { grid-template-columns: auto 1fr; }
      .model-row .actions { grid-column: 1 / -1; justify-content: flex-start; }
    }
    input, select {
      width: 100%; padding: 11px 12px; border-radius: 12px;
      border: 1px solid var(--line); background: #fff; font-size: 0.95rem; color: var(--ink);
    }
    input:focus, select:focus { outline: 2px solid rgba(212, 137, 46, 0.35); border-color: var(--accent); }
    .hint { font-size: 0.8rem; color: var(--muted); margin-top: 8px; line-height: 1.4; }
    .modal-mask {
      position: fixed; inset: 0; background: rgba(42, 34, 28, 0.35);
      display: none; align-items: center; justify-content: center;
      padding: 20px; z-index: 50; backdrop-filter: blur(2px);
    }
    .modal-mask.open { display: flex; }
    .modal {
      width: min(480px, 100%); background: var(--card); border: 1px solid var(--line);
      border-radius: 20px; padding: 22px; box-shadow: 0 24px 60px rgba(40, 28, 16, 0.22);
      max-height: calc(100vh - 40px); overflow: auto;
    }
    .modal-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
    .modal-head h2 { margin: 0; font-size: 1.15rem; }
    .icon-btn {
      width: 34px; height: 34px; padding: 0; border-radius: 50%;
      border: 1px solid var(--line); background: #fff; color: var(--muted); font-size: 1.1rem;
    }
    .modal .desc { margin: 0 0 14px; color: var(--muted); font-size: 0.88rem; }
    label { display: block; font-size: 0.85rem; margin: 12px 0 6px; color: var(--muted); }
    .row { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
    .modal-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 18px; }
    .checkline { display: flex; align-items: center; gap: 8px; margin-top: 14px; font-size: 0.85rem; color: var(--muted); }
    .checkline input { width: auto; }
  </style>
</head>
<body>
  <div class="shell">
    <aside class="nav">
      <div class="brand">DexPet 设置</div>
      <p class="hint">本地配置 · 分区管理</p>
      <button type="button" class="active" data-panel="api">模型管理</button>
      <button type="button" data-panel="pet">宠物</button>
      <button type="button" data-panel="memory">长期记忆</button>
      <button type="button" data-panel="system">系统权限</button>
    </aside>

    <main>
      <!-- Models -->
      <section class="panel active" id="panel_api">
        <h1>模型管理 <span class="badge">LLM</span></h1>
        <p class="sub">管理可用的模型 API。可添加多套配置，点选「使用」切换当前对话模型；可编辑或删除（至少保留一套）。</p>

        <div class="toolbar" style="margin-bottom:14px">
          <button class="primary" id="model_add" type="button">添加模型</button>
          <button class="ghost" id="reload_api" type="button">刷新</button>
          <span class="status" id="api_status"></span>
        </div>

        <div id="model_list" class="model-list"></div>
      </section>

      <!-- PET -->
      <section class="panel" id="panel_pet">
        <h1>宠物 <span class="badge">桌面</span></h1>
        <p class="sub">窗口行为与形象。形象按情绪分别上传，未设置则使用默认绘制猫。</p>

        <div class="block">
          <div class="block-title">窗口</div>
          <div class="toggle-row">
            <div>
              <div class="label">始终置顶</div>
              <div class="desc">开启后宠物浮在其他窗口之上（与右键菜单同步）</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="always_on_top" />
              <span></span>
            </label>
          </div>
          <div class="status" id="pet_status" style="margin-top:10px"></div>
        </div>

        <div class="block">
          <div class="block-title">渲染模式</div>
          <p class="hint" style="margin-top:0">默认精灵帧。Live2D 需自行安装可选依赖并准备已授权模型（不随应用捆绑）。</p>
          <label class="label" for="pet_renderer" style="display:block;margin-bottom:6px;font-weight:600">形象引擎</label>
          <select id="pet_renderer">
            <option value="sprite">精灵帧（默认）</option>
            <option value="live2d">Live2D（用户自备模型）</option>
          </select>
          <label class="label" for="live2d_model_path" style="display:block;margin:14px 0 6px;font-weight:600">Live2D 模型路径</label>
          <input type="text" id="live2d_model_path" placeholder="目录或 *.model3.json 绝对路径" autocomplete="off" />
          <p class="hint">将含 <code>.model3.json</code>（Cubism 3+）或 <code>.model.json</code>（Cubism 2）的模型目录放到本机任意位置，填路径后保存。未安装 <code>live2d-py</code>、路径无效或加载失败时自动回退精灵帧。依赖：<code>pip install -e ".[live2d]"</code>。说明见仓库 <code>desktop/assets/live2d/README.md</code>。</p>
          <div class="toolbar" style="margin-top:12px">
            <button type="button" class="primary" id="save_renderer">保存渲染设置</button>
            <span class="pill off" id="live2d_avail_pill">Live2D 不可用</span>
          </div>
          <div class="status" id="renderer_status" style="margin-top:10px"></div>
        </div>

        <div class="block">
          <div class="block-title">形象（按情绪）</div>
          <p class="hint" style="margin-top:0">精灵帧模式：PNG / JPG / WEBP，建议透明底。上传后约 2 秒桌宠自动刷新。Live2D 模式下情绪尽量映射到模型表情/动作。</p>
          <div class="sprite-grid" id="sprite_grid"></div>
          <div class="status" id="sprite_status"></div>
        </div>
      </section>

      <!-- MEMORY -->
      <section class="panel" id="panel_memory">
        <h1>长期记忆 <span class="badge">本地</span></h1>
        <p class="sub">夜间整理对话为画像与日摘要；白天随机抽检，有值得问的才推气泡。走当前 LLM 配置，数据仅存本机。</p>

        <div class="block">
          <div class="block-title">开关与时刻</div>
          <div class="toggle-row">
            <div>
              <div class="label">启用夜间整理</div>
              <div class="desc">按设定时刻用 LLM 更新 profile 与当日摘要</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="mem_enabled" />
              <span></span>
            </label>
          </div>
          <div class="toggle-row" style="margin-top:12px">
            <div>
              <div class="label">启用主动抽检</div>
              <div class="desc">窗口内随机检查；仍受冷却、聊天中/刚聊完、缺口与规律依据约束</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="mem_proactive" />
              <span></span>
            </label>
          </div>
          <div class="row" style="margin-top:12px">
            <div>
              <label for="mem_digest_hour">整理时刻（时）</label>
              <input id="mem_digest_hour" type="number" min="0" max="23" />
            </div>
            <div>
              <label for="mem_digest_minute">整理时刻（分）</label>
              <input id="mem_digest_minute" type="number" min="0" max="59" />
            </div>
          </div>
          <div class="row">
            <div>
              <label for="mem_window_start">抽检窗口起</label>
              <input id="mem_window_start" placeholder="09:00" />
            </div>
            <div>
              <label for="mem_window_end">抽检窗口止</label>
              <input id="mem_window_end" placeholder="21:30" />
            </div>
          </div>
          <div class="row">
            <div>
              <label for="mem_checks_min">每日抽检次数 min</label>
              <input id="mem_checks_min" type="number" min="1" max="40" />
            </div>
            <div>
              <label for="mem_checks_max">每日抽检次数 max</label>
              <input id="mem_checks_max" type="number" min="1" max="40" />
            </div>
          </div>
          <div class="row">
            <div>
              <label for="mem_max_asks">每日成功提问上限</label>
              <input id="mem_max_asks" type="number" min="0" max="100" />
              <p class="hint" style="margin:6px 0 0">0 = 不限制（默认）；&gt;0 为硬上限</p>
            </div>
            <div>
              <label for="mem_ask_cooldown">成功提问冷却（分钟）</label>
              <input id="mem_ask_cooldown" type="number" min="0" max="1440" />
              <p class="hint" style="margin:6px 0 0">0 = 不限制（默认）；仍保留同规律冷却 / 刚聊完勿扰 / 抽检 min_gap</p>
            </div>
          </div>
          <div class="toggle-row" style="margin-top:12px">
            <div>
              <div class="label">启用轻量晨间</div>
              <div class="desc">固定时刻问候或跟进缺口；默认关，可与随机抽检并存</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="mem_morning" />
              <span></span>
            </label>
          </div>
          <div class="row" style="margin-top:12px">
            <div>
              <label for="mem_morning_hour">晨间时刻（时）</label>
              <input id="mem_morning_hour" type="number" min="0" max="23" />
            </div>
            <div>
              <label for="mem_morning_minute">晨间时刻（分）</label>
              <input id="mem_morning_minute" type="number" min="0" max="59" />
            </div>
          </div>
          <div class="toolbar" style="margin-top:12px">
            <button class="primary" id="mem_save" type="button">保存记忆设置</button>
            <button class="ghost" id="mem_digest_now" type="button">立即整理今日</button>
            <button class="ghost" id="mem_check_now" type="button">立即抽检一次</button>
            <span class="status" id="mem_status"></span>
          </div>
          <p class="hint" id="mem_dir_hint"></p>
          <p class="hint" id="mem_digest_fail" style="display:none;color:#b42318"></p>
        </div>

        <div class="block">
          <div class="block-title">用户画像（可编辑）</div>
          <p class="hint" style="margin-top:0">保存写回 profile.md，下次对话即注入。夜间整理也会覆盖画像；若与整理冲突，保存时会提示确认。</p>
          <textarea id="mem_profile" rows="14" style="width:100%;border:1px solid var(--line);border-radius:12px;padding:12px;font-family:ui-monospace,Menlo,monospace;font-size:0.82rem;background:#fff;color:var(--ink);resize:vertical"></textarea>
          <div class="toolbar" style="margin-top:12px">
            <button class="primary" id="mem_profile_save" type="button">保存画像</button>
            <button class="ghost" id="mem_profile_reload" type="button">重新加载</button>
            <button class="ghost" id="mem_open_dir" type="button">在 Finder 打开目录</button>
            <button class="danger" id="mem_clear" type="button">清空记忆文件</button>
            <span class="status" id="mem_profile_status"></span>
          </div>
        </div>
      </section>

      <!-- SYSTEM -->
      <section class="panel" id="panel_system">
        <h1>系统权限 <span class="badge">安全</span></h1>
        <p class="sub">控制小猫能打开/关闭哪些应用。仅白名单内的应用可通过对话调用 <code>open_app</code> / <code>close_app</code>。</p>

        <div class="block">
          <div class="block-title">应用白名单</div>
          <table class="whitelist">
            <thead>
              <tr><th>别名（对话可用）</th><th>应用程序名</th><th style="width:72px"></th></tr>
            </thead>
            <tbody id="wl_body"></tbody>
          </table>
          <div class="add-row">
            <input id="wl_alias" placeholder="别名，如 chrome" />
            <input id="wl_app" placeholder="应用名，如 Google Chrome" />
            <button class="primary" id="wl_add" type="button">添加</button>
          </div>
          <p class="hint">应用名需与「应用程序」里显示的名称一致（网易云音乐一般为 <code>NeteaseMusic</code>）。添加或删除后会自动保存。</p>
          <div class="toolbar" style="margin-top:12px">
            <button class="ghost" id="wl_reset" type="button">恢复默认</button>
            <span class="status" id="wl_status"></span>
          </div>
        </div>
      </section>
    </main>
  </div>

  <div class="modal-mask" id="modal_mask" role="dialog" aria-modal="true">
    <div class="modal">
      <div class="modal-head">
        <h2 id="modal_title">添加模型</h2>
        <button type="button" class="icon-btn" id="close_modal" aria-label="关闭">×</button>
      </div>
      <p class="desc">配置显示名称、Base URL、模型 ID 与 API Key。Base URL 为 chat completions 前缀。</p>
      <input type="hidden" id="edit_id" value="" />
      <label for="edit_name">显示名称</label>
      <input id="edit_name" placeholder="例如 DeepSeek / 公司网关" />
      <div class="row">
        <div>
          <label for="base_url">Base URL</label>
          <input id="base_url" placeholder="https://api.deepseek.com/v1" />
        </div>
        <div>
          <label for="model">模型 ID</label>
          <input id="model" placeholder="deepseek-chat" />
        </div>
      </div>
      <label for="api_key">API Key</label>
      <input id="api_key" type="password" placeholder="留空则保持现有 Key（新建时请填写）" autocomplete="off" />
      <p class="hint" id="key_hint">尚未保存 API Key</p>
      <label class="checkline">
        <input type="checkbox" id="activate" checked />
        保存后设为当前使用
      </label>
      <div class="modal-actions">
        <button class="primary" id="save" type="button">保存</button>
        <button class="ghost" id="cancel_modal" type="button">取消</button>
        <span class="status" id="modal_status"></span>
      </div>
    </div>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);
    const EMOTION_ORDER = ["idle","happy","curious","thinking","speaking","sad","surprised"];
    let latest = null;
    let whitelist = [];

    function setStatus(el, text, ok) {
      el.textContent = text || "";
      el.className = "status" + (ok === true ? " ok" : ok === false ? " err" : "");
    }

    /* ---- nav ---- */
    document.querySelectorAll(".nav button[data-panel]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".nav button[data-panel]").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        $("panel_" + btn.dataset.panel).classList.add("active");
      });
    });

    /* ---- Models ---- */
    function applyConfig(data) {
      latest = data;
      renderModelList(data);
    }
    function renderModelList(data) {
      const list = $("model_list");
      const profiles = Array.isArray(data.profiles) ? data.profiles : [];
      const active = data.active_profile;
      list.innerHTML = "";
      if (!profiles.length) {
        list.innerHTML = '<div class="hint">暂无模型，请点击「添加模型」。</div>';
        return;
      }
      profiles.forEach((p) => {
        const row = document.createElement("div");
        row.className = "model-row" + (p.id === active ? " active" : "");
        const keyPill = p.api_key_set
          ? '<span class="pill">Key 已配置</span>'
          : '<span class="pill off">Key 未配置</span>';
        const using = p.id === active ? '<span class="tag" style="font-size:0.72rem;padding:2px 8px;border-radius:999px;background:rgba(47,125,74,.12);color:var(--ok)">使用中</span>' : "";
        row.innerHTML =
          '<input class="radio" type="radio" name="active_model" ' + (p.id === active ? "checked" : "") + ' data-activate="' + p.id + '" title="设为当前使用" />' +
          '<div>' +
            '<div class="title">' + (p.name || p.id) + " " + using + "</div>" +
            '<div class="meta"><code>' + (p.model || "—") + "</code> · " + keyPill + "<br/>" + (p.base_url || "—") + "</div>" +
          "</div>" +
          '<div class="actions">' +
            '<button type="button" class="ghost" data-edit="' + p.id + '">编辑</button>' +
            '<button type="button" class="danger" data-del="' + p.id + '"' + (profiles.length <= 1 ? " disabled" : "") + ">删除</button>" +
          "</div>";
        list.appendChild(row);
      });
      list.querySelectorAll("[data-activate]").forEach((el) => {
        el.addEventListener("change", () => {
          if (el.checked) switchActive(el.getAttribute("data-activate"));
        });
      });
      list.querySelectorAll("[data-edit]").forEach((btn) => {
        btn.addEventListener("click", () => openEditModal(btn.getAttribute("data-edit")));
      });
      list.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", () => deleteModel(btn.getAttribute("data-del")));
      });
    }
    async function loadConfig() {
      const res = await fetch("/config");
      if (!res.ok) throw new Error("读取配置失败");
      applyConfig(await res.json());
    }
    function openAddModal() {
      $("modal_title").textContent = "添加模型";
      $("edit_id").value = "";
      $("edit_name").value = "新模型";
      $("base_url").value = "https://api.deepseek.com/v1";
      $("model").value = "deepseek-chat";
      $("api_key").value = "";
      $("key_hint").textContent = "新建时建议填写 API Key";
      $("activate").checked = true;
      setStatus($("modal_status"), "");
      $("modal_mask").classList.add("open");
      $("edit_name").focus();
    }
    function openEditModal(id) {
      const profiles = (latest && latest.profiles) || [];
      const p = profiles.find((x) => x.id === id);
      if (!p) return;
      $("modal_title").textContent = "编辑模型";
      $("edit_id").value = id;
      $("edit_name").value = p.name || "";
      $("base_url").value = p.base_url || "";
      $("model").value = p.model || "";
      $("api_key").value = "";
      $("key_hint").textContent = p.api_key_set
        ? "已保存 API Key（再次输入可覆盖）"
        : "尚未保存 API Key";
      $("activate").checked = latest.active_profile === id;
      setStatus($("modal_status"), "");
      $("modal_mask").classList.add("open");
      $("edit_name").focus();
    }
    function closeModal() {
      $("modal_mask").classList.remove("open");
      setStatus($("modal_status"), "");
    }
    async function switchActive(profileId) {
      setStatus($("api_status"), "切换中…");
      try {
        const res = await fetch("/config/active", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active_profile: profileId }),
        });
        if (!res.ok) throw new Error(await res.text());
        applyConfig(await res.json());
        const name = ((latest.profiles || []).find((p) => p.id === profileId) || {}).name || profileId;
        setStatus($("api_status"), "已切换到「" + name + "」", true);
      } catch (err) {
        setStatus($("api_status"), String(err.message || err), false);
        loadConfig().catch(() => {});
      }
    }
    async function deleteModel(id) {
      const p = ((latest && latest.profiles) || []).find((x) => x.id === id);
      if (!confirm("确定删除「" + ((p && p.name) || id) + "」？")) return;
      setStatus($("api_status"), "删除中…");
      try {
        const res = await fetch("/config/profiles/" + encodeURIComponent(id), { method: "DELETE" });
        if (!res.ok) throw new Error(await res.text());
        applyConfig(await res.json());
        setStatus($("api_status"), "已删除", true);
      } catch (err) {
        setStatus($("api_status"), String(err.message || err), false);
      }
    }
    $("model_add").addEventListener("click", openAddModal);
    $("close_modal").addEventListener("click", closeModal);
    $("cancel_modal").addEventListener("click", closeModal);
    $("modal_mask").addEventListener("click", (e) => { if (e.target === $("modal_mask")) closeModal(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && $("modal_mask").classList.contains("open")) closeModal();
    });
    $("save").addEventListener("click", async () => {
      setStatus($("modal_status"), "保存中…");
      const id = $("edit_id").value.trim();
      const body = {
        name: $("edit_name").value.trim() || "新模型",
        base_url: $("base_url").value.trim(),
        model: $("model").value.trim(),
        activate: $("activate").checked,
      };
      const key = $("api_key").value.trim();
      if (key) body.api_key = key;
      if (!body.base_url || !body.model) {
        setStatus($("modal_status"), "请填写 Base URL 和模型 ID", false);
        return;
      }
      try {
        const res = await fetch(
          id ? "/config/profiles/" + encodeURIComponent(id) : "/config/profiles",
          {
            method: id ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          }
        );
        if (!res.ok) throw new Error(await res.text());
        applyConfig(await res.json());
        setStatus($("modal_status"), "已保存", true);
        setStatus($("api_status"), "模型配置已更新", true);
        setTimeout(closeModal, 350);
      } catch (err) {
        setStatus($("modal_status"), String(err.message || err), false);
      }
    });
    $("reload_api").addEventListener("click", () => {
      loadConfig()
        .then(() => setStatus($("api_status"), "已刷新", true))
        .catch((e) => setStatus($("api_status"), String(e.message || e), false));
    });

    /* ---- Pet ---- */
    function applyPetDisplay(data) {
      $("always_on_top").checked = !!data.always_on_top;
      $("pet_renderer").value = data.renderer === "live2d" ? "live2d" : "sprite";
      $("live2d_model_path").value = data.live2d_model_path || "";
      const pill = $("live2d_avail_pill");
      if (data.live2d_available) {
        pill.className = "pill";
        pill.textContent = data.effective_renderer === "live2d"
          ? "Live2D 生效中"
          : (data.live2d_error ? "已安装，未生效" : "Live2D 可用");
      } else {
        pill.className = "pill off";
        pill.textContent = "未安装 live2d-py";
      }
      if (data.live2d_error && data.renderer === "live2d") {
        setStatus($("renderer_status"), "将回退精灵帧：" + data.live2d_error, false);
      }
    }
    async function loadPet() {
      const res = await fetch("/pet");
      if (!res.ok) throw new Error("读取宠物设置失败");
      const data = await res.json();
      applyPetDisplay(data);
    }
    $("always_on_top").addEventListener("change", async () => {
      const enabled = $("always_on_top").checked;
      setStatus($("pet_status"), "保存中…");
      try {
        const res = await fetch("/pet", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ always_on_top: enabled }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        $("always_on_top").checked = !!data.always_on_top;
        setStatus($("pet_status"), data.always_on_top ? "已开启始终置顶" : "已关闭始终置顶", true);
      } catch (err) {
        $("always_on_top").checked = !enabled;
        setStatus($("pet_status"), String(err.message || err), false);
      }
    });
    $("save_renderer").addEventListener("click", async () => {
      setStatus($("renderer_status"), "保存中…");
      try {
        const res = await fetch("/pet", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            renderer: $("pet_renderer").value,
            live2d_model_path: $("live2d_model_path").value.trim(),
          }),
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        applyPetDisplay(data);
        let msg = "已保存。桌宠将热切换渲染器。";
        if (data.effective_renderer === "live2d") {
          msg = "已保存，Live2D 生效：" + (data.live2d_model_resolved || "");
        } else if (data.renderer === "live2d" && data.live2d_error) {
          msg = "已保存，但回退精灵帧：" + data.live2d_error;
          setStatus($("renderer_status"), msg, false);
          return;
        }
        setStatus($("renderer_status"), msg, true);
      } catch (err) {
        setStatus($("renderer_status"), String(err.message || err), false);
      }
    });

    function renderSprites(sprites) {
      const grid = $("sprite_grid");
      grid.innerHTML = "";
      EMOTION_ORDER.forEach((emotion) => {
        const info = (sprites && sprites[emotion]) || { label: emotion, set: false };
        const card = document.createElement("div");
        card.className = "sprite-card";
        const preview = info.set
          ? '<img src="/sprites/' + emotion + '/image?t=' + Date.now() + '" alt="' + emotion + '" />'
          : '<span class="empty">默认猫</span>';
        card.innerHTML =
          '<div class="label">' + (info.label || emotion) + '</div>' +
          '<div class="sprite-preview">' + preview + '</div>' +
          '<div class="sprite-actions">' +
          '<button type="button" class="primary" data-up="' + emotion + '">上传</button>' +
          '<button type="button" class="ghost" data-del="' + emotion + '"' + (info.set ? "" : " disabled") + '>清除</button>' +
          '</div>' +
          '<input type="file" accept="image/png,image/jpeg,image/webp" data-file="' + emotion + '" hidden />';
        grid.appendChild(card);
      });
      grid.querySelectorAll("[data-up]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const input = grid.querySelector('input[data-file="' + btn.getAttribute("data-up") + '"]');
          if (input) input.click();
        });
      });
      grid.querySelectorAll("input[data-file]").forEach((input) => {
        input.addEventListener("change", async () => {
          const emotion = input.getAttribute("data-file");
          const file = input.files && input.files[0];
          input.value = "";
          if (!file) return;
          setStatus($("sprite_status"), "上传中…");
          const fd = new FormData();
          fd.append("file", file);
          try {
            const res = await fetch("/sprites/" + emotion, { method: "POST", body: fd });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            renderSprites(data.sprites);
            setStatus($("sprite_status"), "已更新「" + emotion + "」", true);
          } catch (err) {
            setStatus($("sprite_status"), String(err.message || err), false);
          }
        });
      });
      grid.querySelectorAll("[data-del]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const emotion = btn.getAttribute("data-del");
          setStatus($("sprite_status"), "清除中…");
          try {
            const res = await fetch("/sprites/" + emotion, { method: "DELETE" });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            renderSprites(data.sprites);
            setStatus($("sprite_status"), "已清除「" + emotion + "」", true);
          } catch (err) {
            setStatus($("sprite_status"), String(err.message || err), false);
          }
        });
      });
    }
    async function loadSprites() {
      const res = await fetch("/sprites");
      if (!res.ok) throw new Error("读取形象失败");
      renderSprites((await res.json()).sprites || {});
    }

    /* ---- Whitelist ---- */
    async function saveWhitelist(okMsg) {
      setStatus($("wl_status"), "保存中…");
      try {
        const res = await fetch("/system/app-whitelist", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ entries: whitelist }),
        });
        if (!res.ok) throw new Error(await res.text());
        whitelist = (await res.json()).entries || [];
        renderWhitelist();
        setStatus($("wl_status"), okMsg || "白名单已保存", true);
      } catch (err) {
        setStatus($("wl_status"), String(err.message || err), false);
      }
    }
    async function loadWhitelist() {
      const res = await fetch("/system/app-whitelist");
      if (!res.ok) throw new Error("读取白名单失败");
      whitelist = (await res.json()).entries || [];
      renderWhitelist();
    }
    function renderWhitelist() {
      const body = $("wl_body");
      body.innerHTML = "";
      if (!whitelist.length) {
        body.innerHTML = '<tr><td colspan="3" style="color:var(--muted)">暂无条目</td></tr>';
        return;
      }
      whitelist.forEach((row, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          "<td>" + row.alias + "</td>" +
          '<td class="app-name">' + row.app + "</td>" +
          '<td><button type="button" class="ghost" data-rm="' + idx + '">删除</button></td>';
        body.appendChild(tr);
      });
      body.querySelectorAll("[data-rm]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          whitelist.splice(Number(btn.getAttribute("data-rm")), 1);
          renderWhitelist();
          await saveWhitelist("已删除并保存");
        });
      });
    }
    $("wl_add").addEventListener("click", async () => {
      const alias = $("wl_alias").value.trim().toLowerCase();
      const app = $("wl_app").value.trim();
      if (!alias || !app) {
        setStatus($("wl_status"), "请填写别名和应用名", false);
        return;
      }
      const existing = whitelist.findIndex((x) => x.alias === alias);
      if (existing >= 0) whitelist[existing] = { alias, app };
      else whitelist.push({ alias, app });
      $("wl_alias").value = "";
      $("wl_app").value = "";
      renderWhitelist();
      await saveWhitelist("已添加并保存");
    });
    $("wl_reset").addEventListener("click", async () => {
      if (!confirm("恢复默认白名单？当前自定义将被覆盖。")) return;
      setStatus($("wl_status"), "恢复中…");
      try {
        const res = await fetch("/system/app-whitelist/reset", { method: "POST" });
        if (!res.ok) throw new Error(await res.text());
        whitelist = (await res.json()).entries || [];
        renderWhitelist();
        setStatus($("wl_status"), "已恢复默认", true);
      } catch (err) {
        setStatus($("wl_status"), String(err.message || err), false);
      }
    });

    /* ---- Memory ---- */
    let memProfileMtime = 0;
    async function loadMemoryProfile() {
      const res = await fetch("/memory/profile");
      if (!res.ok) throw new Error("读取画像失败");
      const data = await res.json();
      $("mem_profile").value = data.content || "";
      memProfileMtime = data.mtime || 0;
    }
    async function loadMemory() {
      const res = await fetch("/config/memory");
      if (!res.ok) throw new Error("读取记忆配置失败");
      const data = await res.json();
      const c = data.config || {};
      $("mem_enabled").checked = !!c.enabled;
      $("mem_proactive").checked = !!c.proactive_enabled;
      $("mem_digest_hour").value = c.digest_hour ?? 0;
      $("mem_digest_minute").value = c.digest_minute ?? 0;
      $("mem_window_start").value = c.proactive_window_start || "09:00";
      $("mem_window_end").value = c.proactive_window_end || "21:30";
      $("mem_checks_min").value = c.proactive_checks_min ?? 10;
      $("mem_checks_max").value = c.proactive_checks_max ?? 20;
      $("mem_max_asks").value = c.proactive_max_asks_per_day ?? 0;
      $("mem_ask_cooldown").value = c.proactive_ask_cooldown_minutes ?? 0;
      $("mem_morning").checked = !!c.proactive_morning_enabled;
      $("mem_morning_hour").value = c.proactive_morning_hour ?? 9;
      $("mem_morning_minute").value = c.proactive_morning_minute ?? 30;
      $("mem_dir_hint").textContent = "目录：" + (data.memory_dir || "");
      const fail = data.digest_failure;
      const failEl = $("mem_digest_fail");
      if (fail && fail.error) {
        failEl.style.display = "block";
        failEl.textContent =
          "最近一次夜间整理失败（" + (fail.at || fail.date || "") + "）：" +
          fail.error +
          "。可点「立即整理今日」重试。";
      } else {
        failEl.style.display = "none";
        failEl.textContent = "";
      }
      await loadMemoryProfile();
    }
    $("mem_save").addEventListener("click", async () => {
      setStatus($("mem_status"), "保存中…");
      try {
        const res = await fetch("/config/memory", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enabled: $("mem_enabled").checked,
            proactive_enabled: $("mem_proactive").checked,
            digest_hour: Number($("mem_digest_hour").value),
            digest_minute: Number($("mem_digest_minute").value),
            proactive_window_start: $("mem_window_start").value.trim(),
            proactive_window_end: $("mem_window_end").value.trim(),
            proactive_checks_min: Number($("mem_checks_min").value),
            proactive_checks_max: Number($("mem_checks_max").value),
            proactive_max_asks_per_day: Number($("mem_max_asks").value),
            proactive_ask_cooldown_minutes: Number($("mem_ask_cooldown").value),
            proactive_morning_enabled: $("mem_morning").checked,
            proactive_morning_hour: Number($("mem_morning_hour").value),
            proactive_morning_minute: Number($("mem_morning_minute").value),
          }),
        });
        if (!res.ok) throw new Error(await res.text());
        await loadMemory();
        setStatus($("mem_status"), "已保存并刷新调度", true);
      } catch (err) {
        setStatus($("mem_status"), String(err.message || err), false);
      }
    });
    $("mem_profile_reload").addEventListener("click", async () => {
      try {
        await loadMemoryProfile();
        setStatus($("mem_profile_status"), "已重新加载", true);
      } catch (err) {
        setStatus($("mem_profile_status"), String(err.message || err), false);
      }
    });
    $("mem_profile_save").addEventListener("click", async () => {
      setStatus($("mem_profile_status"), "保存中…");
      async function putProfile(force) {
        const res = await fetch("/memory/profile", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            content: $("mem_profile").value,
            if_mtime: memProfileMtime,
            force: !!force,
          }),
        });
        return res;
      }
      try {
        let res = await putProfile(false);
        if (res.status === 409) {
          const body = await res.json();
          const detail = body.detail || body;
          const ok = confirm(
            (detail.message || "画像已在别处被修改。") +
              "\\n\\n确定用当前编辑内容覆盖吗？"
          );
          if (!ok) {
            if (detail.content != null) {
              $("mem_profile").value = detail.content;
              memProfileMtime = detail.mtime || 0;
            }
            setStatus($("mem_profile_status"), "已取消，已加载磁盘版本", false);
            return;
          }
          res = await putProfile(true);
        }
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        $("mem_profile").value = data.content || $("mem_profile").value;
        memProfileMtime = data.mtime || 0;
        setStatus($("mem_profile_status"), "画像已保存", true);
      } catch (err) {
        setStatus($("mem_profile_status"), String(err.message || err), false);
      }
    });
    $("mem_digest_now").addEventListener("click", async () => {
      setStatus($("mem_status"), "整理中…");
      try {
        const res = await fetch("/memory/digest?force=true", { method: "POST" });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        await loadMemory();
        setStatus($("mem_status"), data.skipped ? "今日已整理（跳过）" : "整理完成", true);
      } catch (err) {
        setStatus($("mem_status"), String(err.message || err), false);
      }
    });
    $("mem_check_now").addEventListener("click", async () => {
      setStatus($("mem_status"), "抽检中…");
      try {
        const res = await fetch("/memory/check", { method: "POST" });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        setStatus(
          $("mem_status"),
          data.asked ? "已提问：" + (data.question || "") : "未提问（" + (data.reason || "quiet") + "）",
          true
        );
      } catch (err) {
        setStatus($("mem_status"), String(err.message || err), false);
      }
    });
    $("mem_open_dir").addEventListener("click", async () => {
      try {
        const res = await fetch("/memory/open-dir", { method: "POST" });
        if (!res.ok) throw new Error(await res.text());
        setStatus($("mem_status"), "已请求打开目录", true);
      } catch (err) {
        setStatus($("mem_status"), String(err.message || err), false);
      }
    });
    $("mem_clear").addEventListener("click", async () => {
      if (!confirm("清空画像、日摘要与记忆元数据？此操作不可撤销。")) return;
      setStatus($("mem_status"), "清空中…");
      try {
        const res = await fetch("/memory/clear", { method: "POST" });
        if (!res.ok) throw new Error(await res.text());
        await loadMemory();
        setStatus($("mem_status"), "已清空", true);
      } catch (err) {
        setStatus($("mem_status"), String(err.message || err), false);
      }
    });

    /* ---- boot ---- */
    Promise.all([loadConfig(), loadPet(), loadSprites(), loadWhitelist(), loadMemory()]).catch((e) => {
      setStatus($("api_status"), String(e.message || e), false);
    });
  </script>
</body>
</html>
"""
