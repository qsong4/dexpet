# DexPet 记忆系统 Design + Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 夜间用 LLM 整理当日对话为本地文件长期记忆（日摘要 + 用户画像 + **习惯/规律**），对话时注入以「了解用户」，并支持机会驱动的低频主动询问（随机抽检、有问才推；依据 = **记忆缺口** + **规律/习惯**）；与现有 SQLite FTS / 提醒气泡推送复用。

**Architecture:** 在现有 `messages` 持久化与 `memory_fts` 检索之上，新增 `~/Library/Application Support/DexPet/memory/` 文件层（`profile.md` + `daily/YYYY-MM-DD.md`，可选 `patterns.md`）。APScheduler `CronTrigger` 每晚跑整理流水线；运行时将 profile + 近几日摘要注入 system prompt，FTS 作补充检索。主动询问采用 **机会驱动 / 随机抽检**：一天内若干次随机检查窗口，由 LLM 据画像、近日摘要、**缺口**与**习惯/规律**判断「此刻是否值得问」；仅当 `should_ask=true` 时复用 `WsHub` + `MessageType.REMINDER`（或新增 `proactive`）气泡推送，并严格限频。

**Tech Stack:** FastAPI、APScheduler、OpenAI-compatible LLM、SQLite（messages + FTS）、Markdown 文件、PySide6 气泡、`settings` 表配置。

---

## 0. 调研结论（现状）

| 主题 | 现状 | 关键路径 |
| :--- | :--- | :--- |
| 对话存储 | **SQLite 持久化**，非仅内存：`sessions` / `messages` | `backend/db/schema.py`、`backend/db/repository.py` |
| 会话摘要 | 消息过多时 LLM 压缩到 `pet_state[summary:{session_id}]` | `backend/core/history.py` |
| 长期记忆 | 已有 **SQLite FTS5** `memory_fts`；对话后启发式写入 preference/dialogue；按用户输入检索后注入 prompt | `backend/core/memory.py`、`conversation._remember_exchange` |
| 定时任务 | 共享 `BackgroundScheduler`：提醒 `DateTrigger`、股票 `interval`；经 `WsHub.schedule_broadcast` 推桌面 | `backend/app.py`、`plugins/reminder.py`、`plugins/stock.py`、`api/hub.py` |
| Prompt 组装 | `SYSTEM_PERSONA` + 情绪 + 会话摘要 + FTS memory_block + 近 16 条消息 | `conversation.py`、`history.build_context_messages` |
| 主动消息 UI | 已有提醒气泡：`type=reminder` → pause wander(`reminder`) → 展示 8s | `desktop/window.py` ~280–292、`wander.pause/resume` |
| 设置 | `/settings` HTML；`GET /memory?q=` 可搜 FTS；**无**记忆文件查看/清空 UI | `backend/api/http.py`、`settings_page.py` |
| 数据根目录 | `~/Library/Application Support/DexPet/`（`dexpet.db`、`logs/`、`sprites/`） | `backend/paths.py` |

**缺口（相对用户目标）：** 无夜间整理、无可读记忆文件、无滚动用户画像、无习惯/规律提炼、无「主动问用户」流水线、设置页不可控记忆。

---

## 1. 方案对比与推荐

### 方案 A：仅增强 FTS（不写文件）

- 优点：改动小，检索已通。
- 缺点：不符合「落到文件」、用户难审阅/备份、画像难滚动合并。

### 方案 B：仅 Markdown 文件

- 优点：对人可读、易备份。
- 缺点：运行时检索弱；与现有 FTS/测试重复建设。

### 方案 C（推荐）：文件层 + 现有 FTS 混合

- **Source of truth（人可读）**：`memory/profile.md`、`memory/daily/*.md`
- **运行时**：优先注入 profile + 近 N 日摘要；FTS 继续按当前用户句检索片段作补充
- 夜间整理后把画像要点 / 日摘要要点 **upsert 进 FTS**（kind=`profile` / `daily`），保持搜索能力
- 保留现有即时启发式 `add_memory`（可降权或限流，避免噪声淹没）

**默认假设（可拍板）：** 采用方案 C；夜间默认 **00:00 本地时区**；主动询问 **默认开启、机会驱动（随机抽检为主）、严格限频**（见 §2.4、§5）。

---

## 2. 设计

### 2.1 记忆文件结构

根目录（新增 `paths.memory_dir()`）：

```text
~/Library/Application Support/DexPet/memory/
  profile.md                 # 滚动用户画像（Source of truth；含「习惯与规律」段落）
  open_questions.md          # 记忆缺口 / open_loops / 待确认（供抽检判断；可选独立文件）
  patterns.md                # 习惯与规律清单（可选独立文件；与 profile 段落二选一或并存）
  daily/
    2026-08-06.md            # 当日摘要（幂等覆盖）
  meta.json                  # 整理游标、抽检调度、主动问限频与规律问冷却状态等
```

**`profile.md` 建议结构（LLM 输出须遵守）：**

```markdown
# 关于用户

## 稳定事实
- …

## 偏好与习惯
- …（单条偏好；与下方「习惯与规律」区分：此处偏静态偏好陈述）

## 习惯与规律
- …（从多日对话/摘要提炼的高频行为、时间规律、反复主题；每条宜带证据摘要与置信度）
  - 例：工作日上午常问股票行情（置信度：中；依据：近 5 日有 4 日提及）
  - 例：晚间常设提醒（置信度：低；依据仅 2 次）

## 近期关注
- …（可随日滚动，保留最近约 15 条）

## 关系与称呼
- …

## 记忆缺口（供主动抽检）
### open_loops
- …（未闭环事项：承诺过要问、用户说过「回头再说」等）

### 好奇心
- …（宠物想了解但尚无依据的点；须克制，宁缺毋滥）

### 待确认
- …（事实/偏好不确定，需用户一句话确认）
```

**`daily/YYYY-MM-DD.md`：**

```markdown
# 2026-08-06 日摘要

## 要点
- …

## 情绪/互动印象
- …

## 待跟进 / open_loops
- …

## 好奇心 / 待确认
- …（当日新产生的缺口；夜间整理合并进 profile / open_questions.md）

## 当日可观察的行为线索（可选）
- …（请求类型、主题标签等；供多日汇总进「习惯与规律」，勿在此编造时间规律）
```

**`open_questions.md`（可选，机器友好清单）：** 夜间整理可写出结构化列表（每条含 `text`、`priority`、`source`、`created`）；主动抽检优先读此文件，无文件则从 profile / 近日 daily 的缺口章节解析。

**`patterns.md`（可选，机器友好习惯清单）：** 夜间 digest 根据近 N 日 `daily/*.md`（及旧 patterns）滚动更新；建议每条含：

| 字段 | 含义 |
| :--- | :--- |
| `text` | 规律的一句话描述 |
| `kind` | `request_type`（高频请求）\| `time_pattern`（时间规律）\| `theme`（反复主题） |
| `evidence` | 简短依据（如「近 7 日摘要中 5 次提及看盘」） |
| `confidence` | `low` \| `medium` \| `high`（数据不足必须标 low） |
| `last_seen` / `updated` | 便于冷却与过期降权 |

**落盘约定：** MVP 可只在 `profile.md`「习惯与规律」段落维护 3–5 条；增强或抽检需要结构化字段时再落 `patterns.md`（与 profile 段落保持一致，digest 一次写出）。**勿与 open_loops 混写：** 缺口是「还不知道 / 未闭环」；规律是「已经反复观察到」。

**缺口 vs 规律（语义对照）：**

| | 记忆缺口（open_loops / 待确认 / 好奇心） | 习惯与规律（habits / patterns） |
| :--- | :--- | :--- |
| 本质 | 信息不足或事项未闭环 | 多日行为/主题的可复现模式 |
| 典型问法 | 「上次说的 X 后来怎样了？」「你更喜欢 A 还是 B？」 | 「你平时这个点会看盘，今天要帮你看看吗？」 |
| 依据 | 单次或少量对话留下的悬念 | 近 N 日摘要中的频次、时段、主题共现 |
| 风险 | 问太密烦；编造敏感好奇 | 证据不足时瞎猜作息；天天重复同一句 |

**格式权衡：**

| 格式 | 用途 |
| :--- | :--- |
| Markdown | 日摘要与画像：人读、可手改、可进设置页预览 |
| `meta.json` | 机器状态：幂等、重试、规律问冷却键 |
| 不采用 jsonl 作主存储 | 不利于浏览；若以后要审计可另加 `raw/` |

**滚动合并：** 每晚：读旧 `profile.md`（及可选 `patterns.md`）+ 当日对话 + **近 N 日 daily** → LLM 产出**完整新 profile**（有上限字数，如 800–1200 汉字）覆盖写入，并刷新习惯条目；日文件按日幂等覆盖，不无限追加原文对话。

**保留策略（增强阶段）：** 日摘要保留最近 90 天；更早可归档或删除（配置项）。

### 2.2 夜间整理流水线

```text
Cron（可配置 HH:MM）
  → 幂等检查 meta.json.last_success_date == 今日? 则跳过
  → 拉取「本地日历日」内 messages（全 session）
  → 无有效对话 → 写空摘要标记 / 跳过 LLM，仍记成功日期（习惯层可保留旧值）
  → 组装 prompt：旧 profile + 可选旧 patterns + 当日 transcript + **近 N 日 daily**（习惯提炼用）
  → LLM 返回 JSON：{
       daily_md,
       profile_md,                    # 含「习惯与规律」段落
       open_questions[]（缺口）,
       habits[]（3–5 条；kind/evidence/confidence）,
       patterns_md?（若落独立文件）,
       facts_for_fts[]
     }
  → 原子写文件（tmp + rename）：daily + profile（+ 可选 patterns.md / open_questions.md）
  → upsert FTS
  → 更新 meta；失败则记录 retry，次日或 +1h 再试（最多 3 次）
```

**触发：** `CronTrigger(hour=…, minute=…, timezone=本地)`，job id=`memory-nightly-digest`，`replace_existing=True`，`max_instances=1`，`coalesce=True`。配置存 `settings.memory_config` JSON。

**输入来源：** 新增 `Repository.list_messages_between(start_iso, end_iso)`（按 `messages.created_at`；注意库内多为 UTC ISO，边界用本地日 → UTC 换算）。习惯提炼另读近 N 日已写好的 `daily/*.md`（MVP：N=7）。

**Prompt 策略：**

- System：你是记忆整理器；只提取稳定事实/偏好/待办与**有证据的习惯**；禁止编造；时间规律数据不足须标 `confidence=low`；输出严格 JSON。
- 习惯提炼范围（须写入 `habits[]` / profile「习惯与规律」）：
  - **高频请求类型**（如常问股票、常设提醒、常开某类 App）
  - **时间规律**（工作日早上、晚间等——样本不足则 low confidence，宁可不写强断言）
  - **反复主题**（项目、兴趣、人物）
- 温度低（0.2）；无 tools。
- Transcript 预算：例如最多 12k 字符；超长则优先最近消息 + 已有 session summary；近 N 日 daily 另计一小块预算（如 ~2–3k 字）专供习惯汇总。

**失败重试 / 幂等：**

- 成功日写入 `meta.last_success_date`
- 失败：`meta.failures[]`，调度器可用 `DateTrigger` 排队 +1h 重试，或下次 cron 发现昨日未成功则补跑「昨日」
- 同一日历日重复跑：覆盖同名 `daily/日期.md`，profile / habits 以「旧 profile + 该日对话 + 近 N 日 daily」重算（可接受）

**与现有 session summarize 关系：** session 摘要仍服务当轮上下文；夜间记忆面向跨 session 长期画像与习惯，不互相替代。

**习惯层 MVP vs 增强：**

| | MVP | 增强 |
| :--- | :--- | :--- |
| 提炼方式 | 夜间从近 N 日摘要 **启发式和/或 LLM** 产出 **3–5 条** habits | 更细特征统计、跨周稳定度、用户可编辑 |
| 时间规律 | 可写软描述 + confidence；**不**据此自动挂 cron | 高置信时间规律可驱动「准点轻提示」或专用 check 窗口 |
| 落盘 | `profile.md`「习惯与规律」即可 | 可选 `patterns.md` 结构化 + FTS kind=`pattern` |

### 2.3 运行时如何用记忆

`ConversationManager._build_messages` 扩展注入顺序：

1. `SYSTEM_PERSONA` + 本地时间  
2. 情绪 fragment  
3. **长期画像**：`profile.md` 全文（截断至 ~600–800 字；含「习惯与规律」要点，勿整段挤爆预算）  
4. **近 2–3 日** `daily/*.md` 要点（再 ~400 字）  
5. 会话摘要 `summary:{session}`  
6. FTS `search_memory(user_text)` 补充块（limit 3–5；可过滤掉与 profile 重复的短句）  
7. 近 16 条 recent messages  

**Token 预算原则：** 文件记忆块合计硬顶（建议 ~1200 汉字）；超则裁 daily 再裁 FTS；习惯段落随 profile 一并截断，抽检专用路径可另读完整 habits（见 §2.4.2）。

**工具：** MVP **不**暴露 `read_memory` 工具（减少幻觉与泄露面）；增强阶段可加只读 `search_long_term_memory(q)`。

**即时写入：** 保留关键词启发式 preference；dialogue 片段可改为仅在夜间整理进 FTS，或提高门槛（增强），MVP 可暂保留以免行为回退。

### 2.4 主动询问（机会驱动 / 随机抽检）

**目标：** 宠物在合适时机，根据历史记忆判断「此刻是否有值得问用户的点」；**有才问，没有就安静**。依据包括 **记忆缺口** 与 **习惯/规律**，不再默认「只有早上固定问一条」。

**策略定位（相对晨间固定问候）：**

| 模式 | 说明 | 默认 |
| :--- | :--- | :--- |
| **随机抽检（主）** | 一天内若干次随机检查窗口；到点后 LLM 判断 `should_ask` | **推荐默认** |
| **轻量晨间（可选）** | 固定时刻一句短问候 / 或仅当已有高优 open_loop 才问 | **默认关闭**；可与抽检并存 |
| ~~仅晨间固定推送~~ | 旧方案 | **废弃为默认** |

推荐组合：**随机抽检为主 + 可选轻量晨间**（晨间默认关，设置里可开）。

#### 2.4.1 调度

```text
每天本地日开始（或 digest 成功后 / app 启动时）
  → 若 proactive_enabled
  → 在允许时段内采样 K 个互不重叠的检查时刻（随机）
  → 为每个时刻注册 DateTrigger job（id=memory-proactive-check-{date}-{i}）
  → 到点执行 CheckOnce（见下）；多数结果为安静，不推送
```

**配置项（`memory_config` / settings）：**

| 键 | 建议默认 | 含义 |
| :--- | :--- | :--- |
| `proactive_enabled` | `true` | 总开关 |
| `proactive_mode` | `"random_check"` | `random_check` \| `morning_optional` \| `both` |
| `proactive_checks_min` | `10` | 一天随机检查次数下限 |
| `proactive_checks_max` | `20` | 一天随机检查次数上限（每日采样 K∈[min,max]） |
| `proactive_checks_per_day` | `15` | 兼容单值：当 min==max 时用此值；建议默认 15 |
| `proactive_window_start` | `"09:00"` | 允许抽检窗口起点（本地） |
| `proactive_window_end` | `"21:30"` | 允许抽检窗口终点；**避开深夜**（与 digest 00:00 错开） |
| `proactive_min_gap_minutes` | `25` | 两次检查时刻之间的最小间隔（10–20 次/日需短于旧 90min） |
| `proactive_max_asks_per_day` | `0` | **成功提问**日上限；**`0` = 不限制**（非检查次数） |
| `proactive_ask_cooldown_minutes` | `0` | 两次成功提问之间的最小间隔；**`0` = 不限制**（与 max_asks=0 语义一致） |
| `proactive_quiet_after_chat_minutes` | `20` | 刚结束对话后不打扰 |
| `proactive_user_dismiss_cooldown_hours` | `24` | 用户关闭/忽略主动问后的冷却 |
| `proactive_pattern_min_confidence` | `"medium"` | 规律触发类问题的最低置信度（低于此不因规律发问） |
| `proactive_pattern_cooldown_hours` | `48` | **同一规律**再次提问的冷却（避免天天同一句） |
| `proactive_morning_enabled` | `false` | 可选轻量晨间 |
| `proactive_morning_hour/minute` | `9` / `30` | 仅当晨间开启时生效 |

**与忙碌 / 勿扰协调（到点先门闩，再决定是否调 LLM）：**

- `_streaming` / chat pause / 正在输入（若可得）→ **跳过本次检查**（不计入「成功提问」；可选记 `skipped_busy`）
- wander 已因 reminder 暂停 → 跳过，避免叠气泡
- 勿扰：若后续有系统 DND / 用户设置 `proactive_dnd`，直接跳过
- 深夜：窗口外不调度；若机器休眠醒来错过 job，**不补跑堆积**（只保留「仍在窗口内且未过期太多」的下一次，或等次日重采样）

**随机采样算法（MVP 可简）：** 在 `[window_start, window_end]` 均匀随机取 K 个时刻，若两两间隔 < `min_gap` 则重采样（最多 N 次）或贪心拉开。写入 `meta.proactive_schedule[{date}] = [iso…]` 便于调试。

#### 2.4.2 判断（CheckOnce）

到点且通过门闩后：

```text
组装上下文：
  profile.md（画像 + 习惯与规律 + 记忆缺口）
  + 近 2–3 日 daily
  + open_questions.md（若有）
  + patterns.md / habits[]（若独立落盘；否则用 profile 段落）
  + 可选：今日是否已问过、最近一次对话距今多久、
          各规律的 last_asked_at / 冷却剩余、当前本地时刻
→ LLM（低温、无 tools）输出严格 JSON：
  {
    "should_ask": bool,
    "question": string | null,   // 一句自然语言，宠物口吻
    "ask_kind": "gap" | "pattern" | null,  // 缺口跟进 | 规律触发
    "pattern_id": string | null, // 若 ask_kind=pattern，对应习惯条目 id/短键
    "reason": string,            // 内部理由（须能点出证据），不展示或仅日志
    "priority": "low"|"medium"|"high",
    "confidence": "low"|"medium"|"high"  // 规律触发时必填；缺口跟进可省略或沿用缺口优先级
  }
→ 默认偏保守：
    无清晰缺口且无达标规律 / 问题空洞 / 重复近期已问 / 规律证据不足
    → should_ask=false
→ 仅当 should_ask && question 非空 && priority 达门槛（MVP：medium+ 或 high）
   且（若 ask_kind=pattern：confidence ≥ min_confidence 且该规律未在冷却内）
   才进入推送
```

**可问类型（扩展）：**

| 类型 | `ask_kind` | 示例 | 约束 |
| :--- | :--- | :--- | :--- |
| **缺口跟进** | `gap` | 澄清 open_loop / 确认待确认项 | 优先高优 open_loops；好奇心克制 |
| **规律触发** | `pattern` | 「你平时这个点会看盘，今天要帮你看看吗？」 | **必须有证据与置信度**；偏保守；禁止无依据臆测作息 |

**Prompt 原则：**

- 宁可少问：没有具体、有温度、对用户有价值的问题就安静
- 禁止编造用户未提及的敏感话题；优先 `open_loops` / `待确认`，其次 **达标的习惯/规律触发**，再次克制的 `好奇心`
- 规律触发须在 `reason` 中引用证据（频次/近日摘要）；`confidence=low` 不得单独支撑 `should_ask=true`
- 避免天天重复同一规律句：若该 `pattern_id` 仍在冷却 → 换缺口或安静
- 若配置了 `max_asks>0` 且今日已达上限 → **根本不调 LLM**（省费用）；默认 `0` 不限制次数，改由同规律冷却 / 刚聊完勿扰 / min_gap 等门闩防烦
- 若配置了 `ask_cooldown>0` 且距上次成功提问未满间隔 → 跳过（默认 `0` 不启用）
- 若 **缺口全空且无可触发规律**（无 habits，或皆 low confidence / 皆在冷却）→ MVP 可直接 `should_ask=false` 跳过 LLM（增强再允许「轻度寒暄好奇心」）

#### 2.4.3 记忆缺口字段

夜间整理与抽检共用同一套缺口语义：

| 字段 | 含义 | 谁写入 |
| :--- | :--- | :--- |
| `open_loops` | 未闭环：待办跟进、说过要确认的事 | 夜间 digest |
| `好奇心` | 想了解用户但尚无依据 | digest 克制产出；抽检可消费 |
| `待确认` | 画像中不确定条目 | digest |

抽检消费后：可将对应条目标为 `asked` / 从清单移除或降权（写入 `meta` 或更新 `open_questions.md`），避免反复问同一句。

#### 2.4.3b 习惯与规律字段（抽检侧）

与缺口并列、**勿混入 open_questions**：

| 字段 | 含义 | 谁写入 |
| :--- | :--- | :--- |
| `habits` / 「习惯与规律」 | 高频请求、时间规律、反复主题 | 夜间 digest（近 N 日汇总） |

抽检消费规律问后：在 `meta.pattern_ask_cooldown[{pattern_id}] = last_asked_at` 记冷却；**不**因问过就删除该习惯（习惯仍是事实观察，只是暂不重复问）。

#### 2.4.4 防烦

| 规则 | MVP |
| :--- | :--- |
| 每日成功提问上限 | 默认 **不限制**（`proactive_max_asks_per_day=0`；检查仍可 10–20 次） |
| 检查最小间隔 | 时刻采样时 ≥ 25 min（默认；防扎堆） |
| 成功提问冷却 | 默认 **不限制**（`proactive_ask_cooldown_minutes=0`）；`>0` 时 meta 记 `last_proactive_ask_at` 生效 |
| **同一规律问题冷却** | 默认 **48h**（`proactive_pattern_cooldown_hours`）；冷却内不得再以该规律发问 |
| **规律最低置信度** | 默认 **medium**；low 仅可作上下文，不可单独触发推送 |
| 用户关闭/忽略后 | 冷却 24h 不再抽检提问（检查可继续跑但强制不 ask，或暂停调度） |
| 刚聊完不久 | 距最近一条 user/assistant 消息 < 20 min → 跳过 |
| 总开关关闭 | 取消当日未执行的 check jobs；不注册新 job |

#### 2.4.5 推送

**有问题才走现有 reminder/bubble；无问题 = 零推送、无气泡、无声音。**

```text
should_ask == true
  → MemoryProactive.ask(question)
  → hub.schedule_broadcast({ type: "reminder", payload: { title: "DexPet 想问你", message, id } })
  → desktop: wander.pause("reminder") + bubble（与提醒相同）
  → meta: last_proactive_ask_at / proactive_ask_count_today += 1
  → 若 ask_kind=pattern：更新 pattern_ask_cooldown[pattern_id]
```

增强时可新增 `MessageType.PROACTIVE`，桌面共用同一 UI 分支。

#### 2.4.6 与夜间整理的关系

| 夜间整理 | 主动抽检 |
| :--- | :--- |
| 产出 / 刷新 `open_loops`、好奇心、待确认 | **消费**缺口，决定是否缺口跟进 |
| 产出 / 刷新「习惯与规律」/ `habits[]` | **参考**规律，决定是否规律触发（须置信度+冷却） |
| 固定 cron（如 00:00） | 次日窗口内随机 DateTrigger |
| 偏重写文件与画像 | 偏轻量判断 + 偶发推送 |
| 不直接向用户推「今晚想问你」（默认） | 有价值才推 |

整理失败不影响次日抽检（可用旧缺口与旧习惯）；**缺口为空且无可触发规律**则抽检安静。

#### 2.4.7 与 wander / 聊天

同提醒：pause `reminder`；用户关气泡后 resume。不抢占流式对话（`_streaming` → 跳过本次检查）。

### 2.5 隐私与可控

| 能力 | MVP | 增强 |
| :--- | :--- | :--- |
| 在 Finder 打开记忆目录 | 设置页按钮 / slash `/memory` 说明路径 | — |
| 查看 profile / 最近日摘要 | 设置页只读 textarea 或链接 | 可编辑保存 |
| 清空记忆 | 「清空画像+日摘要+可选 FTS」确认 | 分级清空 |
| 开关夜间整理 / 主动询问 | settings JSON + UI | — |
| 整理时刻 / 抽检窗口与次数 | 可配置 | — |

Slash 建议：`/memory` 显示状态与路径；`/memory clear` 需二次确认或仅提示去设置页（防误触）。

数据不出本机；夜间整理走用户已配置的 LLM（与对话同一 profile），**须在设置页标明**。

### 2.6 分阶段落地与验收

#### Phase MVP

1. `memory/` 目录与读写、`meta.json`  
2. 夜间 cron + 从 DB 拉当日消息 + LLM 写 daily + profile（含 **「习惯与规律」3–5 条**，近 N 日摘要启发式/LLM 提炼）  
3. 对话注入 profile + 近日 daily  
4. 设置：启用、时刻、打开目录、清空  
5. 机会驱动主动问：每日 10–20 次随机 check（默认 15 / 可配 min–max），窗口 09:00–21:30，成功提问默认不限次、不设 ask_cooldown（靠同规律冷却 / 刚聊完 / min_gap 等防烦）；判断输入含 **缺口 + 习惯**（可选开关；晨间固定问候默认关）  

**验收：**

- 手动触发 `run_digest(date)` 后出现对应 md，且二次触发不重复计费逻辑正确（幂等）  
- digest 后 profile（或 patterns）含可审阅的习惯条目，且带证据/置信度（或明确 low）  
- 新开对话 system 中含画像关键句  
- 关闭启用后不再调度 LLM  
- 清空后注入块为空、文件重置  
- 抽检：`should_ask=false` 时无气泡；`true` 时气泡弹出；默认不限日次数、不问隔冷却，仍受同规律冷却 / 刚聊完 / min_gap 等约束  
- 规律触发：`confidence` 不足或同规律冷却内 → 不推送；缺口与规律共享每日 ask 上限  
- 忙碌 / 刚聊完门闩生效时跳过且不误计为「已问」  

#### Phase 增强

- FTS 与文件双向同步策略收紧、dialogue 噪声降权  
- 更细空闲信号（桌面心跳）、`PROACTIVE` 消息类型、用户忽略后的智能降权  
- [x] 设置页编辑 profile；抽检窗口 / K / **晨间可选完整 UI + cron 真正注册**（`proactive_morning_*`；关闭移除 job）  
- `search_long_term_memory` 工具  
- 日摘要保留/归档策略、补跑错过的日期  
- **复杂时间规律 → cron/准点轻提示**（高置信 `time_pattern` 驱动专用窗口；MVP 不做）  
- 独立 `patterns.md` + 习惯统计特征、用户可编辑习惯清单  
- [x] 测试与失败通知气泡（「昨晚记忆整理失败」；meta 未读 + 每日最多推一次；成功清除）  

**增强落地备注（2026-08-06）：**

| 项 | 做法 |
| :--- | :--- |
| 可编辑画像 | `GET/PUT /memory/profile`；设置页可编辑 textarea；并发用 `if_mtime` 乐观锁，冲突 409，`force=true` 覆盖（last-write） |
| 晨间可选 | `ensure_jobs` 注册 `memory-proactive-morning` Cron；`morning_check` 复用抽检，无缺口则轻量问候（每日一次） |
| digest 失败通知 | `record_digest_failure` + WsHub reminder 气泡；`digest_failure_notified_date` 防启动重复刷 |

### 2.7 测试要点

- 单元：路径、原子写、幂等 meta、日期边界（UTC vs 本地）  
- 单元：prompt 注入预算截断  
- 单元：频率限制（`max_asks>0` 时同日达上限跳过；`ask_cooldown>0` 时冷却；检查可多次）  
- 单元：随机调度落在窗口内且满足 min_gap；`should_ask=false` 不调 notifier  
- 单元：digest 产出 habits（条数上限、confidence 字段）；缺口与习惯章节不混写  
- 单元：规律触发门闩——low confidence / pattern cooldown / 可选 max_asks / 可选 ask_cooldown  
- 集成：mock LLM 跑 digest → 文件内容与 FTS（含习惯段落）  
- 集成：配置开关关闭时不调用 LLM（含抽检）  
- 桌面：reminder 路径回归（主动问复用时）  
- 不强制真实打 LLM API（一律 mock）  

---

## 3. 关键决策（请用户拍板）

1. **存储形态：** 默认 **方案 C（文件 + FTS）**；若只要文件可改 B。  
2. **夜间默认时间：** 默认 **00:00**。  
3. **主动询问策略：** 默认 **随机抽检为主**（窗口 **09:00–21:30**，每天 **10–20** 次 check 随机采样、建议默认 **15**，成功提问默认不限次、`ask_cooldown=0`，靠同规律冷却 / 刚聊完 / min_gap 防烦）；依据 = **缺口 + 习惯/规律**；**轻量晨间默认关**。若仍想要固定早安，可开 `proactive_morning_enabled`。  
4. **MVP 是否含主动询问：** **已拍板：含**（可关）。  
5. **抽检无依据时是否仍调 LLM：** 默认 **不调**（缺口全空且无可触发规律则安静）；若希望偶发寒暄可改为「低概率调 LLM」。  
6. **习惯落盘：** 默认 MVP 只写 `profile.md`「习惯与规律」；需要结构化冷却键时再加 `patterns.md`（可并存）。  
7. **规律触发保守度：** 默认最低置信度 **medium**、同一规律冷却 **48h**；复杂 cron 时间规律放增强。  

---

## 4. Implementation Plan（按任务执行）

I'm using the writing-plans skill to create the implementation plan below.

### Task 1: 记忆路径与文件 IO

**Files:**
- Modify: `backend/paths.py`
- Create: `backend/core/memory_files.py`
- Test: `tests/test_memory_files.py`

**Step 1: Write the failing test**

```python
def test_memory_dir_and_atomic_profile_write(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.paths.data_dir", lambda: tmp_path)
    from backend.core.memory_files import memory_dir, write_profile, read_profile

    assert memory_dir().name == "memory"
    write_profile("# 关于用户\n\n- 喜欢猫\n")
    assert "喜欢猫" in read_profile()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_memory_files.py::test_memory_dir_and_atomic_profile_write -v`  
Expected: FAIL（模块或函数不存在）

**Step 3: Write minimal implementation**

- `paths.memory_dir()` → `data_dir() / "memory"`，创建 `daily/`  
- `read_profile` / `write_profile` / `read_daily` / `write_daily` / `read_meta` / `write_meta`  
- 写文件：写入 `*.tmp` 后 `os.replace`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_memory_files.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add backend/paths.py backend/core/memory_files.py tests/test_memory_files.py
git commit -m "feat(memory): add markdown memory file helpers"
```

---

### Task 2: Repository 按日查询消息

**Files:**
- Modify: `backend/db/repository.py`
- Test: `tests/test_memory_digest.py`（先写查询部分）

**Step 1: Write the failing test**

```python
def test_list_messages_between_filters_by_created_at(repo):
    # insert 3 messages with controlled created_at
    rows = repo.list_messages_between(start_iso, end_iso)
    assert len(rows) == expected
```

**Step 2: Run → expect FAIL**

**Step 3: Implement**

```python
def list_messages_between(self, start_iso: str, end_iso: str) -> list[dict]:
    rows = self.conn.execute(
        """
        SELECT id, session_id, role, content, created_at
        FROM messages
        WHERE created_at >= ? AND created_at < ?
        ORDER BY id ASC
        """,
        (start_iso, end_iso),
    ).fetchall()
    return [dict(r) for r in rows]
```

**Step 4: pytest PASS → Commit**

```bash
git commit -m "feat(db): list messages in time range for nightly digest"
```

---

### Task 3: Digest 服务（LLM + 幂等）

**Files:**
- Create: `backend/core/memory_digest.py`
- Test: `tests/test_memory_digest.py`

**Step 1: Test with mock LLM**

- 无消息：不调用 LLM，写 meta 成功  
- 有消息：写出 `daily/日期.md` 与更新 `profile.md`（含「习惯与规律」）  
- mock 近 N 日 daily 时可产出 ≤5 条 habits（含 confidence）  
- 同日再跑：`last_success_date` 已是该日则跳过（或 `force=True` 覆盖）

**Step 2: Implement `MemoryDigestService.run(for_date, force=False)`**

- 解析本地日 → UTC 区间  
- Prompt → 要求 JSON：`daily_markdown`, `profile_markdown`（含习惯与规律）, `open_questions`（缺口）, `habits`（3–5 条，含 kind/evidence/confidence）, `fts_facts`  
- 解析失败：整次失败不写半成品（或仅保留旧 profile）  
- 成功后 `add_memory(..., kind="daily"|"profile")` 写入要点（增强可另加 kind=`pattern`）  

**Step 3: pytest PASS → Commit**

```bash
git commit -m "feat(memory): nightly digest service with idempotent meta"
```

---

### Task 4: 挂接 APScheduler Cron

**Files:**
- Create: `backend/core/memory_scheduler.py`（或 `backend/plugins/memory.py` 非 Tool 插件）  
- Modify: `backend/app.py`  
- Test: `tests/test_memory_scheduler.py`（mock scheduler `add_job`）

**Step 1: Test** `ensure_jobs` 根据 config 注册 `memory-nightly-digest`；主动问侧注册当日随机 `memory-proactive-check-*`（或每日重采样 job），**不**默认注册晨间固定 cron

**Step 2: Implement**

- 从 `repo.get_setting_json("memory_config", defaults)` 读：  
  `enabled`, `digest_hour`, `digest_minute`,  
  `proactive_enabled`, `proactive_mode`, `proactive_checks_per_day`,  
  `proactive_window_start/end`, `proactive_max_asks_per_day`,  
  `proactive_pattern_min_confidence`, `proactive_pattern_cooldown_hours`,  
  `proactive_morning_enabled`（默认 false）等（完整见 §2.4.1）  
- Defaults: digest 00:00；proactive 随机抽检 K∈[10,20]（默认单值 15）、窗口 09:00–21:30、min_gap=25、成功提问不限（max_asks=0）、ask_cooldown=0 
- 在 lifespan 里构造服务并 `set_notifier` / 绑定 hub（主动问）  
- digest 在线程中跑：内部用 `asyncio.run_coroutine_threadsafe` 调异步 LLM，或提供同步包装  
- 每日采样检查时刻写入 `meta.proactive_schedule`；关机错过的 job 不堆积补推

**Step 3: PASS → Commit**

```bash
git commit -m "feat(memory): schedule nightly digest and random proactive checks"
```
---

### Task 5: 运行时注入 profile + daily

**Files:**
- Modify: `backend/core/conversation.py`  
- Modify: `backend/core/history.py`（可选：扩展 `build_context_messages`）  
- Test: `tests/test_phase2.py` 或 `tests/test_memory_context.py`

**Step 1: Test** system content 包含「长期画像」且超长被截断

**Step 2: Implement** `format_file_memory_block()`：读 profile + 近 3 日 daily，拼进 system

**Step 3: PASS → Commit**

```bash
git commit -m "feat(memory): inject profile and recent dailies into prompt"
```

---

### Task 6: 主动询问（随机抽检 + 条件推送）

**Files:**
- Create: `backend/core/memory_proactive.py`  
- Modify: `backend/app.py`（notifier / 调度）  
- Test: `tests/test_memory_proactive.py`

**Step 1: Test**

- 缺口为空且无达标习惯，或 mock LLM `should_ask=false` → **不**调用 notifier  
- `should_ask=true`（`ask_kind=gap` 或 `pattern`）且今日未达上限 → 调用 notifier 一次  
- `ask_kind=pattern` 且 confidence 低于门槛 / 同规律冷却内 → 不调用 notifier  
- 可选日上限路径 → `max_asks>0` 时达上限不调用；可选 `ask_cooldown>0`（缺口与规律共享）；默认均为 0 不限制  
- `_streaming` / 刚聊完门闩 → 跳过且不增加 ask count  
- 采样：K 个时刻均在窗口内且满足 min_gap  

**Step 2: Implement** `CheckOnce` + 限频 + 复用 `_push_bubble` / `MessageType.REMINDER`，title=`DexPet 想问你`

**Step 3: PASS → Commit**

```bash
git commit -m "feat(memory): opportunity-driven proactive checks with ask cap"
```

---

### Task 7: 设置 API + 设置页 UI

**Files:**
- Modify: `shared/messages.py`（可选 Pydantic 配置模型）  
- Modify: `backend/api/http.py`：`GET/PUT /config/memory`，`POST /memory/clear`，`POST /memory/digest`（手动触发，便于验收）  
- Modify: `backend/api/settings_page.py`：记忆区块  
- Test: `tests/test_memory_api.py`

**Step 1: API 测试** 改时刻、清空、手动 digest（mock）

**Step 2: 设置页** 开关（整理 / 主动抽检）、digest 时刻、抽检窗口与次数说明、可选晨间开关（默认关）、打开目录、清空按钮、只读预览 profile

**Step 3: PASS → Commit**

```bash
git commit -m "feat(memory): settings API and UI for memory controls"
```

---

### Task 8: Slash 与文档收尾

**Files:**
- Modify: `backend/core/slash.py`（`/memory` 状态）  
- Modify: `tests/test_slash.py`  
- 本计划文档已存在；可在架构设计中加一句交叉引用  

**Step 1–4:** 测试 → 实现 → 提交

```bash
git commit -m "feat(memory): /memory slash status; document cross-links"
```

---

## 5. 建议 MVP 范围（给执行代理）

**做：** Task 1–7（文件、digest、cron、注入、**随机抽检主动问**、设置）  
**缓：** 桌面空闲心跳、可编辑 profile、memory 工具、PROACTIVE 独立消息类型、90 天归档、默认开启轻量晨间、**复杂时间规律 cron/准点提示**、独立 `patterns.md` 完整结构化（MVP 可用 profile 段落代替）  

**MVP 主动问最小落地：**

- 每天 **10–20** 次随机 check（默认 **15**，可配 min/max），窗口 **09:00–21:30**，min_gap **25** min  
- 成功提问默认 **不限次**（`max_asks=0`）、**不问隔冷却**（`ask_cooldown=0`）；无缺口且无可触发规律 / `should_ask=false` → 安静  
- 夜间 digest 默认 **00:00**（可配置）  
- 夜间 digest 提炼 **3–5 条** habits 写入 profile「习惯与规律」（近 N 日摘要；复杂 cron 时间规律不做）  
- 规律触发须 **medium+ 置信度** + **同规律 48h 冷却**  
- 晨间固定问候 **默认关**  
- 推送仅走现有 reminder 气泡  

**手动验收命令示例：**

```bash
pytest tests/test_memory_files.py tests/test_memory_digest.py tests/test_memory_scheduler.py tests/test_memory_context.py tests/test_memory_proactive.py tests/test_memory_api.py -v
curl -X POST http://127.0.0.1:8765/memory/digest   # 若已实现手动触发
open ~/Library/Application\ Support/DexPet/memory
```

---

## 6. 执行交接

Plan complete and saved to `docs/plans/2026-08-06-memory-system.md`.

**Two execution options:**

1. **Subagent-Driven（本会话）** — 每任务新子代理，任务间审查  
2. **Parallel Session（另开会话）** — 使用 executing-plans 按任务批量执行  

（由协调者 / 用户选择；本设计代理不开始大规模实现。）
