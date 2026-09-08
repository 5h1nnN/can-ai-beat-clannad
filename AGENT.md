# CLANNAD Steam 中文版 —— MCP 实时控制 · 已定稿执行计划

> 目标：让 **AI agent 能实时读取并操作 CLANNAD**——暴露实时游戏状态（场景/行号/对话文本/选项），并提供 SL（存取档）/选择/推进/跳转等操作接口，封装成 **MCP 服务**。
> 最近更新：2026-09-04 · 状态：**✅ 阶段 0-3 已完成（跑起中文版 + 状态/控制 + SL 验证），结局检测已定为文本匹配；待阶段 4（MCP Server）**
> 本文档是后续所有工作的**上下文与计划基准**；新会话请先读本文档。

---

## 0. 已确认决策

| # | 决策 | 结论 |
|---|---|---|
| D1 | 技术路线 | **路线 A：基于开源引擎重实现 `siglus_rs` 作游戏内核**（已 clone 于 `e:\dev\siglus_rs`）。不做 hook 原版闭源 exe。 |
| D2 | 运行形态 | **暂保持窗口形态**：跑 `siglus_engine`（siglus_rs 自带窗口版）显示画面，旁路桥接 MCP。headless 仅作为后续可选项（阶段 5）。 |
| D3 | 中文适配 | `SceneZH.pck` 复制为 `Scene.pck`（保底）+ `key.toml` 放 CLANNAD key；`GameexeZH.dat` 引擎已原生识别。 |
| D4 | 文本来源 | 对白以 VM 内部状态为准（dbs 运行期解析），不 OCR。暴露中日对照条目。 |

---

## 1. 结论摘要（TL;DR）

| 项 | 结论 |
|---|---|
| 能否实现 | ✅ 可行 |
| 技术路线 | **`siglus_rs`（Rust 重实现 SiglusEngine）作内核** + 状态/控制接口 + MCP Server |
| 运行形态 | **窗口形态**（可见画面）+ 旁路桥接 |
| 中文版适配 | siglus_rs 已内置 `GameexeZH.dat` 支持；`SceneZH.pck` 复制为 `Scene.pck`（或补丁）；CLANNAD key 经 `key.toml` |
| 本机前置 | 需安装 **Rust 工具链**（当前无 cargo/rustc，C 盘仅 11.4GB → 装 E 盘） |
| 工作量 | 完整版约 2–4 天有效工时（见 §7 里程碑） |
| 仓库 | `e:\dev\siglus_rs` @ commit `577d9c8`（= 官方 pre-release） |

---

## 2. 关键事实（已在本机验证 / 源码确认）

### 2.1 游戏本体
- 引擎：`SiglusEngine_Steam.exe`，VisualArt's Siglus **1.1.134.0**，32 位闭源，无符号
- 场景包：`SceneZH.pck`（228 个 `.ss` 演出/流程脚本，CLANNAD 专属 key 加密）
- 对白库：`dat/text00.dbs` ~ `text23.dbs` —— **日文原文 + 中文译文双列**
- 配置：`GameexeZH.dat`（解出即 `CLANNAD HD` 的 `Gameexe.ini`）
- 存档：`savedata_zh/*.sav`（加密二进制）

### 2.2 文本机制（重要！）
- `.ss` 场景脚本**不含剧情对白**，只有演出指令（bg/cg/bgm/se）与系统文本（逐字/短词存储）
- 场景通过对白标签 **`sdtaXXXX`**（如 `sdta0414`）关联到 dbs 对白库
- 真正的剧情文本在 `text*.dbs`，需 **VM 运行期**解析 dbs 后才知道"当前这句话"
- ⇒ 结论：**"当前对话文本"只能在真正的运行时 VM 里获得**，静态解包拿不到

### 2.3 工具现状
- `SiglusEngine-master/`（Python）：✅ 已验证可完整解包 SceneZH.pck / dbs / GameexeZH.dat。仅静态，无运行时。
- `SiglusExtract.exe/.dll`（X'moe MFC）：❌ 本机运行即崩 `0xC0000005`，且面向旧零售版。

### 2.4 开源引擎重实现 siglus_rs（github.com/xmoezzz/siglus_rs）
源码确认：
- **完整 SiglusEngine VM**：脚本执行、资源加载、渲染(wgpu)、音频、**SL 架构**（`menu_save_slot` / `menu_load_slot` / `write_global_save` / `restore_last_sel_point`）
- **宿主 C ABI**（Windows/macOS/Linux）：
  ```c
  SiglusPumpHandle* siglus_pump_create(const char* game_root_utf8);
  int32_t  siglus_pump_step(SiglusPumpHandle*, uint32_t timeout_ms);   // 逐帧推进
  void     siglus_pump_key_down/up(SiglusPumpHandle*, int32_t key);    // 注入按键
  void     siglus_pump_text_input(SiglusPumpHandle*, const char*);     // 文本
  void     siglus_pump_submit_messagebox_result(SiglusPumpHandle*, u64, i64);
  void     siglus_pump_destroy(SiglusPumpHandle*);
  int32_t  siglus_run_entry(const char* game_root_utf8);              // 完整窗口模式
  ```
- **状态已结构化**：`vm.current_scene_name()` / `current_line_no()` / `is_blocked()` / 消息框 / 选择按钮 `selbtn` / `syscom.pending_proc` 全部是**内部数据字段**，可直接导出
- **中文版适配痕迹**：`find_gameexe_path` 候选含 `GameexeZH.dat`/`GameexeZH.ini`；`GameexeEN/ZHTW/DE/ES/FR...` 一并列出 → 作者已为多语言版设计
- key 机制：项目目录放 `key.toml`，**顶层字段为 `key = [0x.. ×16]`**（源码 `key_toml.rs` 解析为内部 `exe_key16`，注意不要照抄内部字段名写成 `exe_key16=`）；`ScenePckDecodeOptions` = 静态 256B `SCENE_KEY` + 可选 16B exe key；PSB/Emote 另用独立 `emote_key` 字段
- ⚠️ **限制**：`find_scene_pck_path` 目前只认 `Scene.pck` / `Data/Scene.pck`，**不含 `SceneZH.pck`** → 需适配
- 有 **release**（pre-release 577d9c8，2 天前滚动发布，11 assets），作者活跃推进

---

## 3. 路线对比

### 路线 A：siglus_rs 内核 + MCP（✅ 已采用）
```
                    ┌─────────────────────────────────────────┐
  MCP Client (agent)│  MCP Server (Python)                   │
                    │   ├─ 读取: get_status / get_dialogue    │
                    │   ├─ 控制: choose / save / load / jump  │
                    │   └─ 会话变量: set/get_game_variable    │
                    └──────────────┬──────────────────────────┘
                    命名管道/共享内存 │ 状态JSON + 指令队列
                    ┌──────────────▼──────────────────────────┐
                    │ siglus_engine 窗口版 (siglus_rs)         │
                    │  = 完整 Siglus VM + 渲染(wgpu) + SL      │
                    │  新增: host 状态导出 / 指令消费 / 变量表  │
                    └─────────────────────────────────────────┘
```
- ✅ 内部状态全部可获得（对话文本 = dbs 当前条目）
- ✅ 逐帧 pump、可注入按键/鼠标/文本 → 天然支持 agent 驱动
- ✅ 开源，可深度定制，无需逆向闭源 exe
- ⚠️ 需装 Rust；需少量适配 `SceneZH.pck` 命名；渲染用 wgpu（Win10/11 可）

### 路线 B：hook 原版 `SiglusEngine_Steam.exe`
- 需在 32 位无符号 exe 内逆向定位：文本渲染函数、dbs 文本缓冲区指针、选择状态、存档结构
- 对白文本在运行期从 dbs 动态加载 → 要 hook dbs 读取/解码路径才能拿到"当前句"
- 同族工具 `SiglusExtract.exe`（X'moe 自己写的同类 hook）本机已崩溃 → 基建风险高
- ❌ 不推荐（除非路线 A 因渲染/兼容受阻）

**已决策：路线 A（见 §0 D1）。**

---

## 4. CLANNAD 中文版具体适配点

1. **SceneZH.pck 命名**
   - `scene_trace`/`siglus_engine` 走 `find_scene_pck_path` 时只认 `Scene.pck`，但 **`scene_trace --pck SceneZH.pck` 可直接指定路径 → 无头验证零改动**
   - 完整引擎（`siglus_engine`）需在项目目录放 `Scene.pck`（复制/硬链 ← `SceneZH.pck`），或给 `find_scene_pck_path`（`crates/siglus_scene_vm/src/resource.rs`）补丁加入 `SceneZH.pck` 候选（可顺手提上游 PR）
2. **CLANNAD key**
   - 在游戏根放 `key.toml`（README 格式）：
     ```toml
     key = [0x3B, 0x54, 0xDC, 0x74, 0x2F, 0xBA, 0x0C, 0xD6, 0xAC, 0x08, 0xD2, 0x23, 0xEC, 0x60, 0xA9, 0x2E]
     ```
   - 静态 `SCENE_KEY`（256B）已在 `siglus_assets::keys`，无需改
3. **GameexeZH.dat** → siglus_rs 已自动识别 ✅（无需动作）
4. **文本来源**：对白来自 `text*.dbs`（经 `sdtaXXXX`）。MCP 的"当前对话"应暴露 **dbs 中日对照的当前条目**（日文原文 + 中文译文），这正是中文版双列的好处

---

## 5. MCP Server 设计（目标接口）

> 形态：**窗口形态**（见 §0 D2）。MCP Server（Python，stdio 协议）作为独立进程运行；通过 **命名管道/共享内存** 与窗口版 `siglus_engine`（siglus_rs 宿主）双向通信——Server 读状态、发指令。状态以结构化 JSON 返回。

### 5.1 状态类工具（读取）
| 工具 | 返回 |
|---|---|
| `get_status` | 当前场景名、场景号、行号、是否阻塞/等待、播放中BGM/演出 |
| `get_dialogue` | 当前说话人、日文原文、中文译文、dbs源、是否已到选择点 |
| `get_choices` | 若在选择点：选项列表（中日文）、当前高亮 |
| `get_save_list` | 存档槽列表（时间、场景摘要） |
| `get_flags` | 关键剧情 flag / read 进度（可选，后期） |

### 5.2 操作类工具（控制）
| 工具 | 效果 |
|---|---|
| `advance` / `do_click` | 推进对话 / 确认（等价点击/回车） |
| `choose(index)` | 在选择点选第 N 项 |
| `save(slot)` | 写入指定存档槽（复用 `menu_save_slot`+`write_global_save`） |
| `load(slot)` | 读取存档（复用 `menu_load_slot`） |
| `jump(scene[,z])` | 直接跳转某场景（`restart_scene_name`） |
| `skip(to_next_choice)` | 快进到下一选项（设置 skip/auto 状态机） |
| `open_menu(kind)` | 打开系统菜单/返回标题 |

### 5.3 会话全局变量（agent 会话内状态，重要设计点）

> 背景：agent 需要"当次会话内"设定/读取一些全局量，例如**存档数量上限**、**进入坏结局次数**、当前扮演策略、禁止触碰的 flag 区间等。MCP 协议本身无此设施，但**在 MCP Server 进程内维护一张变量表**即可实现（每次 `tools/call` 虽是独立请求，但 server 进程在同一会话内常驻、共享状态）。

**语义分层（务必区分，决定变量存哪一层）：**

| 变量类别 | 示例 | 存放层 | 生命周期 |
|---|---|---|---|
| ① agent 会话内约定（仅供 agent 参考/自约束） | 存档上限=3、本次走渚线、不用跳转 | **MCP Server 内存表** | 会话结束即失 |
| ② 引擎强制生效（引擎必须真正执行） | 真的只允许 N 个槽；坏结局后重置本线 | **siglus_rs 内核**（`globals.extra_vars` 新增），MCP 负责传入 | 随引擎运行 |
| ③ 自动统计（应由事件驱动，禁 agent 手写） | 进入坏结局次数、已读行数、当前周目 | 桥接层**事件累加**，MCP 只读 | 会话/落盘 |
| ④ 跨会话长期记录 | 累计通关次数、全 CG 进度 | 落盘 `state.json`，启动加载 | 持久 |

**对应 MCP 工具设计：**
- `set_game_variable(name, value, scope=session|engine|persistent)` —— 写变量
- `get_game_variable(name)` —— 读变量（含自动统计的只读项）
- `list_game_variables()` —— 列出当前全部变量（便于 agent 复盘）
- 引擎强制项（如存档上限）由桥接层在下发 `save()` 前检查，或由引擎内核读取 `globals.extra_vars` 直接拦截

**关键原则：**
- ② 要真正"强制"必须下沉到引擎内核，不能只靠 agent 自觉；
- ③（坏结局次数这类）应由桥接层**在检测到 ending/flag 时自动 +1**，agent 只读，避免漏数/数错；
- 变量表建议以 JSON 序列化存于 MCP Server 内存，可按 scope 决定是否落盘。

### 5.4 事件推送（可选，便于 agent 实时响应）
- `dialogue.changed`、`choice.appeared`、`save.completed`、`game_variable.changed`（通过 MCP `notifications` / SSE）

---

## 6. siglus_rs 侧需要新增的"桥"（含代码级挂载点）

> 已 clone 源码到 `E:\7_projects\clannad_mcp\siglus_rs`（commit `577d9c8`，与最新 pre-release 一致）并定位到精确挂载点。以下均为**已读源码确认**的改动位置。

### 6.1 状态导出挂载点（读）
| 数据 | 位置（源码） | 说明 |
|---|---|---|
| 当前场景/行号 | `SiglusHost::debug_status_summary()` / `vm.current_scene_name()/current_line_no()` | 已存在，直接用 |
| **当前对话文本** | `crates/.../forms/stage.rs` → `cd_text_current_mwnd()` 内 `m.msg_text.push_str(accepted)`；`ctx.ui.append_message()` | 加一行：把 `accepted` 写入共享状态/回调即可 |
| **当前说话人** | `stage.rs` → `cd_name_current_mwnd()` 内 `m.name_text` | 同上 |
| 消息框/翻页状态 | `MwndState`（`globals.rs`）含 `msg_text`、分页、按键图标、`key_icon_appear` 等 | 结构化，直接导出 |
| 选择按钮状态 | `MwndSelectionState` / `MwndSelectionChoice` / `BtnSelItemState`（`globals.rs`） | 选项列表可直接枚举 |
| 阻塞/等待类型 | `ctx.wait` / `is_blocked()` / `flow.stack` | 判断"在等什么" |
| 存档槽 | `syscom::menu_save_slot / menu_load_slot / write_global_save` | 已有实现，MCP 直接调 |

### 6.2 控制注入挂载点（写）
| 操作 | 方式 |
|---|---|
| 推进/点击 | `SiglusHost::key_down(Enter)` 或 `mouse_down` / `touch`；或直接调 VM 的按键处理 |
| 选择第 N 项 | 设置选择状态结果 / 模拟对应按键坐标 |
| 存档/读档 | 直接调 `syscom::menu_save_slot(ctx,..)` + `write_global_save` / `menu_load_slot(ctx,..)` |
| 跳场景 | `vm.restart_scene_name(&scene, z)`（`perform_return_to_menu` 同款） |
| 快进 | 设 `script.skip_trigger` / `auto_mode_flag`（`ScriptRuntimeState`） |
| **会话变量/引擎强制项** | 新增 `globals.extra_vars: HashMap<String,Value>`（或挂 `CommandContext`）；存/读档上限等由 `syscom::menu_save_slot` 读取该表决定是否放行；坏结局计数由桥接层检测 ending flag 时自动累加 |

### 6.3 桥接形态（已定：窗口形态）

- **✅ 窗口形态 + 旁路（已定 D2）**：跑 `siglus_engine`（siglus_rs 自带窗口版，渲染 wgpu，显示可见画面）。桥接层通过 **命名管道/共享内存** 与 MCP Server 通信：
  - 每帧 step 后，宿主把状态 JSON（scene/line/对话/选项/阻塞）写到共享区
  - MCP 指令（点击/选择/存读档/跳转）写入命令队列，宿主消费
  - 好处：agent 驱动同时**人可见过程**；引擎渲染问题可独立调试
- 嵌入式（无头）保留为阶段 5 可选项，本阶段不做

### 6.4 无头验证入口（阶段 1 用，无需渲染）
- `crates/siglus_scene_vm/src/bin/scene_trace.rs`：`scene_trace --pck <SceneZH.pck> --project <dir> --scene seen0414`
  - **用 `--pck` 直接指定路径 → 绕开 `SceneZH.pck` 命名限制**（不必复制改名）
  - 直接跑 VM 并打印 TEXT/NAME，可先验证对白文本正确
  - 它读 `ScenePckDecodeOptions::from_project_dir` → 项目根 `key.toml` 提供 CLANNAD key

---

## 7. 分阶段实施蓝图

### 阶段 0（环境，~1h）
- 安装 Rust：`winget install Rustlang.Rustup`
- 在 `E:\7_projects\clannad_mcp\siglus_rs` 跑通 `cargo build -p siglus_scene_vm --bin scene_trace`（先冒烟）
- 本机 GPU/Win10/11 渲染冒烟测试（`siglus_engine` 对仓库自带 testcase）

### 阶段 1（跑起中文版，~0.5–1天）
- 复制 `SceneZH.pck` → `Scene.pck`（或补丁 `find_scene_pck_path`）
- 放 `key.toml`（CLANNAD key）
- 用 `scene_trace`/`siglus_engine` 跑到标题画面与开头剧情，验证：能进游戏、能翻页、文本正确
- ⚠️ 风险点：CLANNAD 特殊演出（seen6800 等纯指令、DREAMS）、字体/PSB 资源；若卡住则记录并针对性修 VM

### 阶段 2（状态导出，~0.5–1天）
- 在宿主层加 `state_json()`：scene/line/对话(dbs当前条目)/选择/阻塞
- 先把对话文本来源打通（dbs 加载路径 → 当前句）

### 阶段 3（控制注入，~0.5天）
- `advance/choose/save/load/jump` 通过 host 方法实现并自测
- 用 `siglus_pump_*` 走通按键/鼠标注入路径

### 阶段 4（MCP Server + 会话变量，~0.5–1天）
- Python MCP Server（stdio），命名管道/共享内存桥接
- `get_status/get_dialogue/get_choices/advance/choose/save/load/jump`
- **会话变量表**（§5.3）：`set/get/list_game_variable`；引擎强制项接 `globals.extra_vars`；坏结局等事件自动统计
- 本地用一个假 agent / 脚本端到端验证"读一句→选一项→存个档→读档"闭环

### 阶段 5（打磨，可选）
- 事件推送、flag 查询、多存档槽 UI、headless 模式（隐藏窗口）

---

## 8. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 中文版特殊资源/演出不被 siglus_rs 支持 | 阶段1卡住 | 先用 `scene_trace` 无窗口定位问题；对照源码补 VM 指令；必要时提 issue/PR 给作者 |
| `SceneZH.pck` 命名不被识别 | 无法启动 | 复制为 `Scene.pck` 保底 + 给上游补 `SceneZH.pck` 候选 |
| 字体（中文渲染） | 中文显示异常 | 确认中文版用系统字体还是内嵌；调 wgpu 字体配置 |
| 渲染(wgpu)在某些环境失败 | 窗口无法出画面 | 先用 `scene_trace` 无头验证逻辑与文本（不依赖渲染）；wgpu 问题单独排查（驱动/特性）；headless 仅作阶段 5 备选 |
| CLANNAD key 不匹配 | 解密失败 | 本机已在 `KeyList.txt` 验证过该 key 可解 SceneZH.pck ✅ |
| 对话文本与画面不同步 | 状态暴露不准 | 在 VM 的 dbs 加载点挂钩，文本以 VM 内部状态为准（非 OCR） |

---

## 9. 下一步执行清单（新会话从这开始）

> 决策已定（见 §0）。直接按序执行即可。

### ✅ 已就绪
- [x] `siglus_rs` 已 clone 至 `E:\7_projects\clannad_mcp\siglus_rs`（commit `577d9c8`）
- [x] MCP 挂载点已定位（§6.1/6.2）
- [x] 环境：git 2.51 ✅ / winget ✅ / E 盘 43GB ✅

### ⬜ 待执行（阶段 0 → 阶段 1）

- [x] **安装 Rust** —— 2026-09-04 完成：rustup 1.98.1 GNU 工具链（无 MSVC），装于 `E:\.rustup` / `E:\.cargo`（User 级 RUSTUP_HOME/CARGO_HOME/PATH 已写入；因 static.rust-lang.org 极慢，经 USTC 镜像 `RUSTUP_DIST_SERVER=https://mirrors.ustc.edu.cn/rust-static` 安装成功）
- [x] `cargo build -p siglus_scene_vm --bin scene_trace` 冒烟 —— ✅（dev 8m20s；同时构建了 siglus_engine）
- [x] 游戏根放 `key.toml`（CLANNAD key，见 §4）
- [x] `scene_trace --pck <SceneZH.pck> --project <游戏根> --scene seen0414` 验证对白输出 —— ⚠️ 已确认 pck 解密+场景 17 可读；纯 scene_trace 遇 wait 会空转（无帧 tick），对白验证改用自定义无头探针（见下）
- [x] 复制 `SceneZH.pck` → `Scene.pck`（游戏根内已建 Scene.pck）
- [x] **跑 `siglus_engine` 窗口版 → 跑到标题画面** —— ✅ 自动按 Enter 驱动后到达 `_system_title`（日志 `engine_click2.err.log`），截图 `capture_click2.png`
- [x] 验收点：能进游戏 ✅、能翻页 ✅（Enter 推进/换行正常）、文本正确 ✅（探针读 VM 消息窗状态输出简体中文，见 `probe_0414_zh.log`）
- [x] 代码修复已提交 siglus_rs @ `fb51a19`（见 §11 改动记录）

### 阶段 0/1 实际操作要点（2026-09-04 实测）

1. **运行入口（窗口形态）**：`target\debug\siglus_engine.exe --project-dir E:\SteamLibrary\steamapps\common\CLANNAD`；配合自动化按键脚本 `diagnostics/scripts/run_engine_click.ps1`（向窗口发 Enter）。
2. **无头文本验证（新增 bin）**：`E:\7_projects\clannad_mcp\siglus_rs\target\debug\clannad_probe.exe --project <游戏根> --scene seen0414 --frames 1500 --click --click-every 40`。设置 `SIGLUS_LANGUAGE=ZH` 得到简体中文列（默认 JP 列）。探针逐帧 tick + 注入 Enter，打印 `scene/line/blocked/name/text/choices`（文本直接读 VM 的 `MwndState.msg_text/name_text`，即阶段 2 状态导出的基础）。
3. **语言列**：textXX.dbs 第 0 列=日文、第 2 列=简中；脚本经 `SYSTEM.GET_LANGUAGE`（`ctx.globals.system.language_code`，可用环境变量 `SIGLUS_LANGUAGE` 或配置覆盖）选列。
4. **已知噪音（可接受）**：开局旧式 name-template 链 `[108]/[131]/[158]` 未实现 → 现已 warn-once 跳过（名字窗可能缺定制名字，文本不受影响）；`database.name.missing:DATABASE.21` 为 cgmodetbl 表名缺失，无碍推进。

### 阶段 1 卡点与已修 Bug（重要！）

| 卡点 | 根因 | 修复 |
|---|---|---|
| dbs 全部 `lzss: arc_size out of bounds` | CLANNAD ZH dbs 的 arc_size=整包长（含 8B 头），严格解包越界 8B | `siglus_assets::dbs` 改用 `lzss_unpack_lenient`（原版即按 org_size 解码）|
| scene 起始 `unhandled form command chain [108]` 即 bail | 旧式 name 参数链未实现，且未处理即硬错 | `vm.rs`：warn-once 跳过 + 按 ret_form 向 ctx 栈推默认值（fork PR#5 同方向）|
| debug 构建 `multiply with overflow` 崩溃（text_render.rs:1890）| 像素混合 `u16` 乘法 255³ 溢出 | 改 u32 运算（语义不变）|
| scene_trace/纯 run() 空转 | 场景 wait（timewait/翻页等待）需帧 tick 驱动 | 无头用 `run_script_proc + tick_frame`（title_probe/clannad_probe 模式）|

> 说明：`siglus_ss_decompiler`（本仓库自带）可把场景反编译为可读 .ss（如 `diagnostics/evidence/seen0414.ss`），是排查演出脚本的利器。

### 证据文件（`E:\7_projects\clannad_mcp\diagnostics\evidence\`）
- `capture_click2.png`（1.9MB）——窗口版标题画面 `_system_title` 渲染帧
- `engine_click2.err.log` —— 窗口版全流程日志（scene=_system_title 于 3000 帧）
- `probe_0414_zh.log` —— 无头 ZH 探针输出（幻想世界 seen6900 → seen0414，朋也名字窗、中文对白逐行）
- `probe_0414b.log` —— 同场景日文列对照
- `seen0414.ss` —— seen0414 反编译脚本
- `scene_list.txt` —— Scene.pck 全部 228 个场景名与索引
- `capture_title.png`/`capture2.png` —— 早期引导画面帧

> 之后按 §7 阶段 2→5 推进（状态导出 → 控制注入 → MCP Server → 会话变量 → 打磨）。

---

## 11. 阶段 0/1 改动记录（2026-09-04）

### siglus_rs（本地仓库，commit `fb51a19`，基线上游 `577d9c8`）
| 文件 | 改动 |
|---|---|
| `crates/siglus_assets/src/dbs.rs` | DBS LZSS 改用 lenient 解包（CLANNAD ZH arc_size 含头 8B） |
| `crates/siglus_scene_vm/src/vm.rs` | 未处理 form 链 warn-once 跳过并按 ret_form 推 ctx 默认值（对齐上游 open PR #5 方向：https://github.com/xmoezzz/siglus_rs/pull/5） |
| `crates/siglus_scene_vm/src/text_render.rs` | 像素 alpha 混合改 u32（修 debug 溢出崩溃） |
| `crates/siglus_scene_vm/src/bin/clannad_probe.rs`（新增）+ `Cargo.toml` | 无头驱动/对白状态探针 bin |

### 游戏目录（E:\SteamLibrary\steamapps\common\CLANNAD）
- 新增 `key.toml`（CLANNAD Steam 简中 16B key）
- 新增 `Scene.pck`（= SceneZH.pck 副本，14.2MB）
- 未改动任何原版文件；savedata_zh 未写入（测试未存档）

### 本机环境
- Rust：`E:\.rustup` / `E:\.cargo`（stable-x86_64-pc-windows-gnu 1.98.1），User 环境变量已持久化；crates.io 直连可用，如需可配 rsproxy 镜像
- 工具二进制：`E:\7_projects\clannad_mcp\siglus_rs\target\debug\{siglus_engine,scene_trace,clannad_probe,siglus_ss_decompiler}.exe`
- 复现窗口版标题：`powershell -File E:\7_projects\clannad_mcp\diagnostics\scripts\run_engine_click.ps1`
- 复现无头 ZH 对白：`set SIGLUS_LANGUAGE=ZH && E:\7_projects\clannad_mcp\siglus_rs\target\debug\clannad_probe.exe --project E:\SteamLibrary\steamapps\common\CLANNAD --scene seen0414 --click`

---

## 12. 游玩缺陷修复记录（2026-09-04 round2，commit `e874fe2`）

### 已修复：中文字符 □ / 缺字
- 根因：GameexeZH.dat 配置字体 `CONFIG.FONT.NAME = "Noto Sans Mono CJK SC Regular"`（官方字体在 dat/NotoSansMonoCJKsc-Regular.otf），但引擎①只扫 font/fonts、②SYSCOM 初始配置惰性 → 实际用 MS ゴシック（缺简体字形）。
- 修复：font 候选目录加入 `dat/`；`apply_gameexe_runtime_defaults` 在 CommandContext 创建时即用 `syscom::original_config_defaults` 应用 Gameexe 配置（字体/消息速度/音量等）。

### 窗口态实测（本轮二进制，2026-09-04）
| 场景 | debug 结果 | 备注 |
|---|---|---|
| NEW GAME（标题 row410）| 自动翻页 100s+ 无崩溃；无按键时 line 冻结（不会自动推进）| seen6900→seen0414 |
| CONFIG（row518）| 进入稳定；方向键/Enter/ESC 操作 55s 无崩溃 | 旧二进制的“进入即闪”未复现 |
| LOAD（row464 → `_system_loadsave`）| 可进入；debug≈4.7fps、release≈11.3fps | 页面本身重；release 仍略卡，待后续优化 |
| story 场景 | debug≈43fps | |

### 存档目录事实
- 引擎读写目录 = `<project>/savedata`（大小写不敏感命中原版 `SAVEDATA`，即用户 Steam 原存档 config/global/read.sav）。
- 原存档槽 .sav 不在 savedata_zh/SAVEDATA 顶层列表中；LOAD 页为空槽时依然慢 → 卡顿来自页面合成本身，非存档枚举。

### 待办（依赖用户复测反馈）
- 用户确认用新 debug/release 重测 NEW GAME / CONFIG / LOAD；
- 若仍有闪退：用户跑 `E:\7_projects\clannad_mcp\diagnostics\scripts\user_repro_capture.ps1` 复现，回传 `diagnostics/logs/userrun_*.err.log`（含 RUST_BACKTRACE=full）；
- LOAD 页 11fps 优化留待后续（页面合成热点需 profile）。

---

## 13. round2 追加：CONFIG 页空白问题（commit `955ad53`，仍待收敛）
- 用户反馈：CONFIG 不再崩溃，但进入后页面全空白（无任何设置项）；游戏内右键菜单同样空白；右键可正常返回。
- 进展：
  - 无头探针验证：`_system_config` 场景会停在其主循环 line400（blocked=false）且 stage 表单内**无任何内容对象** → 内容缺失发生在 VM 层，非渲染层；
  - 已确认并实现此前被跳过的 `GLOBAL.GET_SCENE_NAME/GET_LINE_NO`（131/158）→ 配置场景内不再有 skipped chain，但空内容仍复现（还需更深根因）；
  - fork(AetherSiglus) 的改动聚焦名字窗布局/存档，非配置 UI，不直接适用。
- 存档目录事实：引擎用 `<project>/savedata`（命中原版 SAVEDATA，即真实 Steam 存档）。
- 下一步：等用户复测（含 diagnostics/scripts/user_repro_capture.ps1 日志）或提供“是否连面板/边框都没有”等界面细节，再沿 syscom 自定义 UI 机制追（CLANNAD config 为自研 EXCALL UI）。

---

## 14. 阶段1后运行期修复与 MCP 决议（2026-09-04）

### 14.1 本轮（阶段1后）所有提交
| commit | 内容 |
|---|---|
| `fb51a19` | 阶段0/1 基础修复：dbs lenient 解包 / 未处理 form 链跳过+ctx 默认 / text_render u32 溢出 / clannad_probe 工具 |
| `e874fe2` | 字体：扫描 `dat/`、CommandContext 创建即应用 Gameexe SYSCOM 初始配置（修复中文 口 缺字） |
| `955ad53` | 实现 `GLOBAL.GET_SCENE_NAME/GET_LINE_NO`（form 131/158，此前被跳、返回空/0） |
| `6d472e2` | 诊断口：`SG_STAGE_DUMP`/`SG_SPRITE_CNT`（env 门控的内容/提交计数） |

### 14.2 三大用户问题最终判定
| 用户反馈 | 结论 |
|---|---|
| NEW GAME：黑白/口/自动推进/数秒闪退 | **已修**（字体+配置初始化）；实测连跑 100s+ 无崩溃；**无输入时不自动推进**（此前“自动推进”来自连点/Enter 连发脚本）；黑白色=开场幻想世界本身样式 |
| LOAD 存档页极卡顿 | debug≈4.7fps / **release≈11.3fps**（页面合成重；推荐 release 运行）；**槽位本身也不显示**（属下面 EXCALL 缺口） |
| CONFIG 页闪退 | **不再闪退**；但**内容空白**（属 EXCALL 缺口） |

### 14.3 关键发现：系统覆盖层(EXCALL)菜单画面不渲染【已知缺口，非 MCP 阻塞】
- CONFIG / 游戏内右键(CANCEL) / LOAD 槽位 共用 `_system_common` 的 **EXCALL 共享壳**（`form49`+EXCALL 镜像 `form16433`，各 303 对象/33 消息窗），场景经 `suspend_wait_for_syscom_excall` 进入。
- 实测：壳已建，但每帧**只有 2~3 个可见对象、消息窗文本为空、提交的可见 sprite 极少**（对比标题页稳定 12 个有效 sprite）。灰遮罩/背景正常 → 覆盖层机制在工作，**缺的是子对象图像/文本绑定与提交渲染**。
- 普通图层（标题/剧情/过场）完全正常 ⇒ 问题定位为**引擎未实现 EXCALL 系统覆盖层内容渲染**；上游 fork(AetherSiglus) 改动不含此部分，无可直接移植实现。
- 结论：**“元素与功能”层面基本完善**（场景逻辑、syscom 状态、配置值、遮罩均正常），仅画面内容未画（部分菜单文字可能同样未填充，同属此缺口）。
- **对 MCP：不阻塞**（读=VM 内部状态；写=内部接口，均不依赖画面）。

### 14.4 目标重定向（已更新 goal revision4）
> 推进 MCP 阶段2+：状态读取接口（scene/line/name/text/choices/save_slots）+ 控制接口（advance/choose/save/load/jump）并验证存读档与选择点数据；为阶段4 MCP Server 铺路。EXCALL 菜单渲染列为独立已知缺口，不纳入。

### 14.5 待办（按序）
- [ ] 阶段2：状态导出/读接口（基于 clannad_probe 现有读取：scene/line/blocked/name/text/choices，可扩展 save_slots/flags）
- [ ] 阶段3：控制接口 advance/choose/save/load/jump；无头验证**选择点读取+选择**、**save/load 数据写读**（尚未实测）
- [ ] 阶段4：MCP Server（stdio）封装
- [ ] （独立项）EXCALL 覆盖层渲染：需对照 Siglus C++ 实现 `tnm_syscom`/EXCALL 绑定渲染；本会话无视觉模型，视觉闭环可交由后续或用户辅助
- [ ] （minor）返回标题需两次左键（覆盖层退出后 focus/button-group 复位）

### 14.6 工具/命令速查
- 抓日志复现：`powershell -ExecutionPolicy Bypass -File E:\7_projects\clannad_mcp\diagnostics\scripts\user_repro_capture.ps1`（输出 `diagnostics/logs/userrun_*.err.log`，含 RUST_BACKTRACE=full）
- 运行引擎：`E:\7_projects\clannad_mcp\siglus_rs\target\debug\siglus_engine.exe --project-dir "E:\SteamLibrary\steamapps\common\CLANNAD"`（release 版性能更好）
- 无头对白/状态探针：`E:\7_projects\clannad_mcp\siglus_rs\target\debug\clannad_probe.exe --project <游戏根> --scene seen0414 --click`；`SIGLUS_LANGUAGE=ZH` 取简中列
- 诊断口：`set SG_STAGE_DUMP=1`（内容/提交计数，需打开对应页面时查看）
- 证据：`diagnostics\evidence\`（标题截图/日志/脚本反编译/场景索引）——测试产物统一归档于 `diagnostics\`（logs/screenshots/scripts/evidence），已被 `.gitignore` 忽略，不入库

### 14.7 项目结构（本仓库=clannad_mcp 父仓库 + 子仓库 siglus_rs）
- 父仓库 `E:\7_projects\clannad_mcp`（git）：由 `AGENT.md` + `.gitignore` + `.gitmodules` 组成，并把 `siglus_rs` 作为**子仓库(gitlink)** 固定到提交指针。
- `siglus_rs`：已重定向 `origin` → `https://github.com/5h1nnN/siglus_rs.git`（不再指向 xmoezzz/siglus_rs），已把全部改动推送到 fork（`main` @ `63e3578`）。
- `diagnostics\`：测试截图/日志/脚本/反编译证据（本地，.gitignore 忽略）。
- 首次克隆本仓库后：`git submodule update --init` 即可拉取 fork 的 siglus_rs。
- 说明：本地 `siglus_rs` 直接保留了原克隆的 8GB 构建产物（`target/` 已被子仓库自身的 .gitignore 忽略），无需重编、未删除目录；“删除 xmoezzz/siglus_rs” 落实为**移除对上游的引用**（origin 已指向 fork）。

---

## 15. 阶段2/3 进展（2026-09-04，多模态会话，commit `01e602e`）

### 15.1 已交付
- **`clannad_ctl`**（新增 bin，无头）：状态/控制驱动。每帧输出 JSON：
  - 读：`get_status`（scene/scene_no/line/blocked）、`get_dialogue`（name/text）、`get_choices`（btnsel 文案）、`save_slots`（数量）。
  - 写：`advance`（Enter）、`choose`（`ctx.request_sel_point_with_result`）、`save/load`（`syscom::menu_save_slot/menu_load_slot`+`write_global_save`）、`jump`（`restart_scene_name`）。
- **引擎 `SG_CTL`**（env 门控 + `ctx_state_json` 状态导出）：可在运行中的窗口态引擎按帧调度 `SAVE/LOAD/JUMP/CHOOSE/STATE@FRAME`，打印 JSON。
- **隔离工程 `clannad_test`**（junction 指向 dat/g00/gan/bgm/mov/wav/koe + Scene.pck/key.toml + 空 savedata）：SL 测试不触碰真实 Steam 存档。

### 15.2 已验证
- 状态 JSON 读取正确（scene/line/name/text/choices/save_slots）。
- **advance / choose / save / load / jump** 控制接口均已在引擎接线；验证运行中 **save 已真正写盘**（隔离 savedata 生成 `config.sav/global.sav/read.sav`）。
- 窗口态：标题页（NEW GAME/LOAD/CONFIG/STAFF/EXIT 英文菜单）与剧情中文文本渲染完全正常（多模态截图确认）；无崩溃。

### 15.3 已知阻塞（下一优先）
- **无头深推剧情会在 `_cl_forclannad` 下溢**：`PROPERTY elm=[]`（参数链为空）+ `ASSIGN` 对空元素作字符串出栈 → `str stack underflow @ pc=0x13d6 line144`（`clannad_ctl`/无头深走都会触发，窗口态游戏不受影响）。将与 131/158 无关（A/B 已验证）。
  - 影响：无头模式暂无法顺畅推进到**选择点**与**完整 SL 恢复**的确定性验证；需先修该引擎缺陷（包含调用的参数链/空元素处理）。
- 修完后即可完成：真实选择点读取+choose 分支；save→jump→load 恢复到原场景的闭环验证。

### 15.4 下一步
1. 修 `_cl_forclannad` 空参数链 ASSIGN 下溢（含调用参数传递）。
2. 无头驱动到真实选择点验证 `get_choices` + `choose`。
3. 无头 `save→jump→load` 恢复到原 scene/line 的闭环断言。
4. 之后按阶段4 把 `clannad_ctl` 的状态/控制接口封装为 MCP Server（stdio）。

---

## 16. 阶段2/3 收尾结论与 MCP 形态决议（2026-09-04）

### 16.1 已完成
- `clannad_ctl`（无头状态/控制驱动）+ 引擎 `SG_CTL`/`ctx_state_json` 已提交（`01e602e`）；隔离工程 `clannad_test`（junction + 空 savedata）。
- 已验证：状态 JSON（scene/line/name/text/choices/save_slots）读取正确；advance/choose/save/load/jump 全部接线；**save 已真实写盘**（config/global/read.sav）。
- 多模态截图确认：标题页菜单(NEW GAME/LOAD/CONFIG/STAFF/EXIT)与剧情中文文本渲染完全正常，无崩溃。

### 16.2 无头深推的引擎缺口（真实根因，已定位未修复）
- `_cl_forclannad` 包含调用($mes/$dbs_select 等)在无头深推时：
  - `ASSIGN` 的 STR 实参未入栈 → `str stack underflow @ pc=0x13d*`；
  - 继续是 `assign_call_prop_result` 对 include-call 参数 form=20 `sub=[0]` 不支持。
- 尝试“空串掩码 + call-prop no-op 容错”后，脚本通过多行但**陷入无限循环**（line 144→339 反复），因为 include 的字符串实参并未真正生效 → **已回退这两处容错**（避免掩盖/挂起；窗口态完全不受影响）。
- 真正修法是**实现 include-call（`cur_call.*` / `CALL.L/K` / `__elm` 参数）的字符串实参传递与 form=20 赋值**，属中等以上引擎工作量。

### 16.3 MCP 形态建议（据此选择）
- 结论：**MCP 走“窗口态引擎 + 桥”（AGENT.md §6.3 路线 A 窗口形态）最稳**——引擎已可实时读状态（SG_CTL/状态导出）与发控制（advance/choose/save/load/jump）；无头深推只作可选增强。
- 下一阶段4：把 `clannad_ctl` 的状态/控制逻辑用 **stdio 命名管道/共享内存桥** 对接窗口态引擎（复用现有 host 按键/鼠标注入 + syscom SL），封装成 MCP Server。
- 若仍需完全无头（便于 CI/测试），则先实现 §16.2 的 include-call 实参传递，再跑真实选择点 + save→jump→load 闭环。

### 16.4 工作区整理（已执行）
- `E:\7_projects\clannad_mcp` 已建 git 仓库，`siglus_rs` 为子模块。
- 测试脚本/日志/截图/反编译/证据/隔离工程统一移入 `diagnostics/`（根 `.gitignore` 忽略 `diagnostics/`、`*.log/*.png/*.ss/*.ps1`，不入库）。
- `AGENT.md` 命令速查中路径已随迁移更新（见下）。

---

## 17. 结局检测方案重定（2026-09-04，多模态会话，commit `df6d7c3`→`5864f84`）

> **背景（重要）**：用户提出 MCP 需要"结局相关接口"。我在探索中发现最初假设（"结局=有 Steam 成就的场景"）**是错的**，并经历多轮否定后，最终把结局检测定为**文本匹配**。本节记录：权威事实、被否定的信号、以及最终实现。

### 17.1 用户提供的权威结局清单（TRUE END）
```
共有 11 个 TRUE END：美佐枝Misae、智代Tomoyo、有纪宁Yukine、杏Kyou、椋Ryou、
胜平Kappei、春原兄妹Mei、琴美Kotomi、风子Fūko、渚Nagisa、幸村Koumura。
其余还有十几个坏结局。剩余的 steam 成就都不是结局。
TRUE END 结束一定会：播放 ED → 获得光玉 → 返回标题（成就在 ED 播放结束后才解锁）。
```

### 17.2 被否定/错误的信号（逐个验证过，记下来避免重走）
| 信号 | 为什么不能用 |
|---|---|
| **Steam 成就** | ① 游戏内只有 **16 个字面 `ach_xxx`**（椋/春原梅/渚/幸村无对应成就）；② **engine 里 `ctx.ids.steam_set_achievement` 硬编码为 0**（constants.rs:3071），`steam.rs` 的 `if id != 0` 永远假 → **VM 运行期不记录 set_achievement**，成就不可观测；③ 成就是账户级一次性。 |
| **`return_to_menu`** | 太宽泛：很多"路线后端/章节结束"场景也调用，非结局专用。 |
| **`g[123] += 1`（光玉）** | **坏结局也 +1**（seen0666 春原bad end 同样执行），不能区分 TRUE END vs 坏结局。 |
| **`g[1004..1006]` 终值** | TRUE END 间取值不一（seen9999=1,1,2；seen5430=1,1,0；seen7500=0,0,0），不统一。 |
| **"播放ED"命令** | 全场景无固定的 `mov.play`(ED) 调用；TRUE END 与坏结局的**命令词汇表基本一致**（唯一差异 `syscom.set`，且坏结局是子集）。 |
| **以 scene 对白末句定位** | `.ss` 场景的 `$mes(serial)` **不按显示顺序排列**（一个 scene 跨数万行、多分支），按文件位置取"最后几句"必然错。用户用风子线实况（"请和风子交往吧！"）验证了这一点。 |

### 17.3 最终方案：文本匹配判定（用户拍板，判句由用户提供）
- 原理：MCP / clannad_ctl **每帧读当前对话窗文字**（`current_msg_text`，即 VM 的 `MwndState.msg_text`），与 `endings_map.toml` 的**判定句**做匹配，命中即判定"达成某结局"并上报。
- 优点：不依赖成就/场景结构；每次显示都触发（非一次性）；判句用户可从实况直接给出。
- `endings_map.toml` 格式改为：`"判定句" = "结局名"`；`@` 前缀 = 整行精确匹配（默认子串）；实际显示带 `「」『』“”""` 框，比对时 `strip_dialogue_quotes` 先剥框。

### 17.4 判句唯一性验证 + scene 定位（用 `clannad_text --search`）
工具 `clannad_text`（bin，见 §17.6）加 `--search`/`--search-file` 模式，可在全部 text dbs 里搜判句。11 个 TRUE END 判句**各恰好 1 次命中**（无撞句），且定位到对应角色路线场景：

| 结局 | 判句serial | 定位场景 | 备注 |
|---|---|---|---|
| 风子 | 4110290 | seen1518 | 与成就场景一致 |
| 杏 | 2118230 | seen3514 | 一致 |
| 胜平 | 11031400 | seen7600 | 一致 |
| 有纪宁 | 8052830 | seen5430 | 一致 |
| 智代 | 5089390 | seen2514 | 智代线 |
| 春原梅 | 7053710 | seen7400 | 春原兄妹 |
| 幸村 | 9001970 | seen7300 | |
| 琴美 | 3115100 | seen4800 | 距离60 |
| 椋 | 2074260 | seen3506 | 距离190 |
| 渚 | 18149630 | seen6726 | After Story 渚 |
| 美佐枝 | 10027680 | seen7500 | 距离580 |

（"距离"= 判句serial 与场景 `$mes` 记录范围首尾的差距，都很小。）

### 17.5 已实现文本匹配判定（clannad_ctl，commit `457187c`+`5864f84`）
- `clannad_ctl` 每帧：读当前文字 → 与 map 判定句匹配（子串/`@`精确）→ 命中上报
  `{"event":"ending","kind":"text","name":"<结局名>","phrase":"<判定句>","scene","line","frame"}`；`HashSet` 去重（同句停留不重复触发）。
- 保留 `return_to_menu` 作为**信息性 `route.end` 事件**（非权威结局判定）。
- 新增 `--test-match <text>` / `--test-match-file <utf8.txt>` 验证模式（配合 `--endings-map`），无需跑完整游戏即可测试判句命中。
- **实测验证**：
  - `「请和风子交往吧！」`（带框，子串）→ ✅ `风子 Fuko TRUE END`
  - `一直都喜欢着…朋也你。`（`@`精确）→ ✅ `杏 Kyou TRUE END`
  - `普通的学校对话，不会命中。`（负例）→ ✅ 不命中

### 17.6 新工具 `clannad_text`（bin）
- 读取 `text*.dbs`（UTF-8 UTF16 按需），按游戏 `$mes` 算法还原对白：`db_no = serial/1_000_000`，`row = db.find_num(500, serial)`，`get_str(row, 0)=日文 / get_str(row, 2)=中文`。
- 模式：`--scene-ss <scene.ss>` 列出该场景全部对白（中日对照）；`--search <substr>`/`--search-file <utf8.txt>` 在全部 dbs 里搜判句；`--probe` 打印各 dbs 行列类型。
- 起因：headless 深推被 `_cl_forclannad` 缺口卡住（§16.2），无法跑到对白，故直接读 dbs。
- ⚠️ 中文判句/参数请走 **`--search-file <utf8.txt>`**（Rust 按 UTF-8 读文件），避免 PowerShell 命令行列中文被 GBK 风马牛。

### 17.7 关键教训（务必牢记）
- `.ss` 场景**不含剧情对白**（只有 `$mes(serial)` 引用），对白在 `text*.dbs`，`$mes` 序列**非按显示顺序** → 静态按文件位置取"末句/首句"不可靠。
- 用户对游戏（实况/真相）的判断**优先**于一切静态推断；本会话多次因我静态猜 scene/信号而被用户用实况纠正。
- 引擎 `steam_set_achievement` id=0 → 成就运行时不可观测，是硬事实（constants.rs:3071 + steam.rs:22）。
- 文本匹配是当前唯一被验证可行、用户认可的结局判定方式。

### 17.8 下一步
- [ ] **阶段4 MCP Server（stdio）**：封装 `clannad_ctl` 状态/控制 + 文本匹配结局。这是主线目标。
- [ ] （可选增强）窗口态引擎跑真实对白验证文本判定在真实对话下触发。
- [ ] （独立项）`_cl_forclannad` include-call 实参缺口（§16.2）若修好，可让 headless 顺畅走到选择点/SL，但非 MCP 阻塞。

> 说明：`endings_map.toml`（诊断工程内）由用户填了 11 个 TRUE END 判定句，已用 `clannad_text --search` 验证唯一性并定位场景。文本判定逻辑已提交并通过 `--test-match` 实测。

---

## 18. 阶段2/3 接口定稿（2026-09-04，commit `ab63b64` 等）

### 18.1 状态/事件/控制接口现况（`clannad_ctl`，无头+引擎 `SG_CTL` 共用状态源）
- **读取（轮询，仅核心 + 日期）**
  - `get_status` → `{scene, scene_no, line, blocked, name(说话人), text(当前对白), choices[], save_slots[], date}`
  - 其中 **date** 是唯一保留“内容”的：`{"month":4,"day":14,"weekday":1,"text":"4月14日 星期一"}`（未到日期剧情点为 `null`）。
- **事件（变化信号，内容不展开）**
  - `bgm.changed`、`background.changed`、`portrait.changed` —— 仅当对应集合变化时返回（不透明 id 列表；首个观测仅建基线不输出）。
  - `choice.appeared`（+自动 `choose`）、`ending`（按判定短语匹配）、`route.end`（return_to_menu/end_game）。
- **控制**：`advance`、`choose`、`save`、`load`、`jump`（`syscom::menu_save_slot/menu_load_slot`、`request_sel_point_with_result`、`restart_scene_name`）。
- **flag：按需求跳过**；**bgm/背景/立绘不做完整 id→名称映射**（id 太多不现实 → 改用“变化信号”，仅日期保留内容）。

### 18.2 变更与取舍
- 之前尝试过“资源 id→可读名称映射（nl_map.toml，45 bgm/503 bg/25 chr）”因条目过多、且 id→名称需人工/官方名单核证，**已废弃**；`nl_map.toml` 已删除，代码无残留引用。
- 文件后期被改写加入 **结局/返标题检测**（`endings_map.toml`、`__all_endings.txt`、`ending_pending`/`match_ending`）——予以保留并与本模型共存（`ending`/`route.end` 事件）。
- 已知引擎缺口（未修）：无头深推剧情在 `_cl_forclannad` include-call 字符串实参处会 `str stack underflow`/`call-prop form=20` 不支持；窗口态游玩不受影响。

### 18.3 交付/环境
- 提交：`fb51a19, e874fe2, 955ad53, 6d472e2, 01e602e, 106d111, f9884f9, b4ff920, ab63b64`（阶段0/1 + 阶段2/3 + 状态事件化）。
- 隔离工程 `diagnostics/clannad_test`（junction + 空 savedata + `endings_map.toml`/`__all_endings.txt`），不触碰真实 Steam 存档。
- 工作区已整理：测试脚本/日志/截图/反编译/证据统一在 `diagnostics/`（根 `.gitignore` 忽略，不入库）；`siglus_rs` 为子模块。

### 18.4 下一步（阶段4）
- 把上述接口封装为 **MCP Server（stdio）**：读取工具 `get_status/get_dialogue/get_choices/get_save_list`，通知事件 `bgm.changed/background.changed/portrait.changed/choice.appeared/ending/route.end`，控制工具 `advance/choose/save/load/jump`。
- 可选：窗口态桥接（引擎 `SG_CTL` + 状态/事件导出）作为 MCP 后端；无头深推受 §18.2 缺口限制，暂以窗口态为准。

---

## 19. 快进 / 跳过到下一选项（2026-09-04，commit `3577cec`）

### 功能
- 引擎 `skip_to_next_choice(max)`：**一帧内突发循环**逐页推进——每页 `ctx.ui.reveal_message_now()`（瞬间显示完当前句）+ Enter 翻页 + `run_script_proc`/`tick_frame`——直到**出现真实选项**（`globals.selbtn`，即 CLANNAD `$mes_sel`，见 §19.3）、VM 停住或达到 `max` 步数。
- 过程中收集整段对白（每行 name/text），结束以 `[CTL] skip| ...` 打印整段，并打印 `skip: choice reached ... choices=[...]`。
- 触发：**游戏内按 Ctrl** 或环境变量 `SG_CTL = "SKIP:MAX@FRAME"`。
- 用途：把“上百次 advance”合并为一次 `skip`，直接返回到下一选项点的整段文本/状态，供 MCP 使用。

### 帧率说明（用户关心点）
- **不受渲染/VSync 帧率限制**：快进在单次 redraw 内跑多个 VM 步（reveal-now + Enter 不依赖真实时间的打字机等待），是 CPU 密集型突发，低帧率下同样能瞬间快进。

### 验证状态（诚实说明）
- 代码已编译通过（`siglus_engine`）。
- 窗口态自动化在本机会话**偶发稳定**（标题/剧情截图、部分页打开成功过，但空句柄导致多次失败），加上无头深推受 §16.2 `_cl_forclannad` 缺口限制，**尚未在这次自动运行中拿到完整的 `[CTL] skip` 输出证据**。
- 手动验证方法：
  - 运行 `E:\7_projects\clannad_mcp\siglus_rs\target\debug\siglus_engine.exe --project-dir "...\diagnostics\clannad_test"`（或游戏根）
  - 进入剧情后**按 Ctrl**（或对窗口态用 `SG_CTL=SKIP:4000@<frame>`）→ 应快速推进到下一选项并打印整段 `[CTL] skip| ...`。

### 19.1 引导修复（重要）
- 之前用 `clannad_test` 跑引擎会 panic `vm init: scene not found: _start`，根因是**隔离目录缺 `GameexeZH.dat`**（junction 只连了 dat/g00/…，根文件的 GameexeZH.dat 未拷贝）→ 引擎解不出 `START_SCENE` → 回退默认 `_start` → Scene.pck 无此场景。
- 修复：把游戏根 `GameexeZH.dat` 拷入 `clannad_test`（已验证可引导到 `_system_adv`、无 `_start` panic）。
- 注意：**重建 `clannad_test` 时必须同时拷贝 `key.toml`、`Scene.pck`、`GameexeZH.dat`** 并建立资源 junction。
- 附：wgpu/loader 的 `SocialClubVulkanLayer.json` 等 ERROR 属无害噪音（缺失 VK layer 文件），不影响运行。
- 下轮接入 MCP 时可复用 `skip`（SG_CTL/宿主方法）替代大量 advance。
- 结束另打印 **`[CTL] skip.segment {json}`**：一次性返回 `{scene,line,lines:[{name,text}...],choices:[...],state:{...}}`，便于 MCP 直接取整段。

### 复用/兼容
- 未改动外部已提交的 `clannad_ctl`/`clannad_text`/结局检测逻辑；仅在 `siglus_engine` 增加 skip；`AGENT.md` 其余段落保持外部更新。

### 19.2 实测反馈修复（commit `22fc69e`）
- **变日语**：之前须设 `SIGLUS_LANGUAGE=ZH`；现已改为**检测到 `GameexeZH.dat` 即默认 ZH**（未显式设语言时），无需环境变量。
- **Ctrl 卡死/未响应**：根因①按住 Ctrl 触发系统按键**自动重复** → 每次重复都启动一次 4000 步突发循环；②单次突发在**同一帧内不停推进、不给渲染/消息泵让路**。
  修复：
  - 仅 **Ctrl 首按**（`!repeat`）触发；已触发或 VM 已停则 no-op。
  - 快进改为**状态化渐进**（`SKIP_BURST` 页操作后让路给渲染），窗口持续显示、不再“未响应”但音乐照播。
  - 结束仍一次性打印整段 `[CTL] skip| ...` 与 `skip.segment {json}`。
- 附带说明：早期日志里 skip 在 seen0414 收集 82 行后继续，最终到 `_system_language` 遇 `unknown opcode=0x2d` 停止。该 `0x2d` **并非真正的独立引擎缺口**，而是 `GLOBAL.SELMSG`（选项命令）未实现导致 VM 把操作数当 opcode 读——见 §19.4（已修复）。

### 19.3 卡顿 & 真选项（selbtn）修复（commit `2fe2310`）
- **快进仍非常卡**：原因是 `SKIP_BURST=64` 每帧塞太多 VM 步，渲染/消息泵负担重。把 `SKIP_BURST` 降到 **12**，每帧页操作更少、让路更频繁，明显减负（CPU 突发仍瞬时）。
- **卡在选项前一句（「这种东西根本没办法听…」）无法推进**：根因是 CLANNAD 的真实选项是 **`globals.selbtn`**（`$mes_sel` → `BtnSelectRuntimeState`，`BtnSelectChoiceState.text` 存选项文本），旧代码检测的是 `btnselitem_lists`（不是 CLANNAD 的选项机制），所以一直判定“无选项”而跳过；且虽然停在了选项处，**未渲染的选项浮层**挡住推进，点左键/Ctrl 都没反应。
  修复：
  - 新增 `ctl_selbtn_active`/`ctl_selbtn_choices`/`ctl_selbtn_cursor`，skip 改为**检测并停在 selbtn 选项**，选项文本从 `globals.selbtn.choices` 输出（而非 btnselitem_lists）。
  - 在 selbtn 选项处**再按一次 Ctrl** → 自动选中高亮项（`ctl_selbtn_cursor`）继续推进，不再死锁。
  - `skip.segment {json}` 的 `choices` 现在返回真实 CLANNAD 选项文本。
- 验证提示：进入剧情按一次 Ctrl → 应推进到**真实选项**（selbtn）并停住、返回该选项文本；在选项处再按 Ctrl → 自动选中高亮项进入下段。

### 19.4 真正的根因：`GLOBAL.SELMSG` 选项命令未实现（commit `ad0654e`，成功）
- 核心问题：**CLANNAD `$mes_sel` 选项编译后是 `GLOBAL.SELMSG`（form 100）/ `SELMSG_CANCEL`（102），而 `dispatch_global_form` 完全没有处理这两个 form**（只处理了 `SELBTN` 76/77/126/127/128）。
- 后果：VM 走到第一个选项时**不认识 `SELMSG`** → `[warn] unhandled form command chain [100], skipping` → **从不弹出选项**（`globals.selbtn.choices` 恒空，之前 §19.3 读 selbtn 时误以为选项走 SELBTN，实际是 SELMSG）→ VM 跳过命令后继续走，把紧随的操作数字节 `0x2d` 当成 opcode → **`unknown opcode=0x2d` 停机**。
- 这也解释了为什么**普通点击推进也一样卡住**（不是 skip 的锅，是引擎缺 `SELMSG` 指令）、为什么卡在选项前两句、以及为什么在 `seen0414:697` 的 COMMAND 之后立即撞 `0x2d`。
- **修复**：在 `dispatch_selbtn_command` 里把 `GLOBAL.SELMSG`/`SELMSG_CANCEL` 映射成 `SELBTN`/`SELBTN_CANCEL` 处理——解析选项文本进 `globals.selbtn.choices`、置 `started=true`、`wait_key()` 让 VM 真正停在选项处等待选择。这样选项既被呈现，也能被 MCP/skip 层读到；`0x2d` 停机随之消失。
- **验证**（本次运行，skip_trace.log）：
  - 不再 `0x2d` 停机，`halted=false`、`unknown_opcodes=""`。
  - 停在 `seen0414:697`，`selbtn_started=true`、`selbtn_choices=2`、`wait=[key]`（真正等待选择）。
  - 一次 Ctrl 即停对（不再要按两次）；选项处再按 Ctrl（`retrigger@choice picked=0`）自动选中高亮项，继续推进到**下一个选项** `seen3415:135`（`selbtn_choices=2`，「好像说过火了。」）——整条选择链路打通。
- 附：之前为定位此问题加的工程级修复与诊断（提交于本会话）：`f3e8cd8`（selbtn 检测需 `started` + skip trace）、`ee6ed43`（time-wait 快进）、`03e6d21`/`7b1e093`/`2f3dfe7`/`be87e04`（停机上下文/opcode 历史/SG_CMD_TRACE 诊断）。其中 `fcb2a1e`（跨场景 COMMAND 提前返回）只对**真正换 scene 的 FARCALL** 生效；`seen6900:17 CD_NONE` 那次是它误伤同场景消息 COMMAND 的回归，已收窄为仅 scene 变化时提前返回。

### 19.5 帧率优化（profiling 定位 + 惰性 mwnd 刷新）
- **性能剖析**（`SG_REDRAW_TIMER` + `SG_CTX_TICK_TRACE` 细分）：正常游玩每帧 `tick_ms≈8~13ms`、`frame_plan_ms≈2ms`、`render_ms≈4ms`、`TOTAL≈15~18ms`，卡在 60fps 附近。其中最大头是 **`ui.tick`**（每帧 ~3ms、与 delta 无关）。
- **真正的大头是 `tick_additional_mwnds`（实测 ~45ms/帧）**：`ui.tick` → `tick_additional_mwnds` 遍历 `mwnd_instances`（CLANNAD 每场景常驻多个额外消息窗实例），**每个都完整执行 `tick_mwnd_only`**（窗框/头像/按键/emoji 图刷新 + 文本重焙 + 布局重建），**无论是否可见**。这同时解释“进新场景更卡”（场景内 mwnd 实例多）。
- **修复（`cfe687d`）— 惰性 mwnd 刷新**：`tick_mwnd_only` 里，便宜的动画更新 + 字体扫描每帧仍跑；但当 mwnd **完全隐藏、不在动画中、且无内容/投影** 时，跳过昂贵的 `refresh_*`/文本重焙/布局重建。隐藏 mwnd 无屏幕精灵可重建，一变成可见立即响应。正常游玩显著流畅。
- **快进步数（`261a115`）**：`SKIP_BURST` 从 12 降到 **4**（每帧最多 4 页操作），Ctrl 快进更平滑、每帧 VM 步负担更低。
- 残余：**进入新场景仍有一次 ~0.5s 暂停** —— 属一次性成本（新场景 g00 背景首次同步解码 + 首次字體/文本烘焙 + wgpu 首次管线/纹理上传）。正常游玩已流畅；如需彻底消除，需异步/延迟资源加载（改动较大，暂缓）。
- 诊断说明：本次会话加的 `SG_UI_TICK_TRACE`/`SG_MWND_TICK_TRACE`/`ctx_tick_mark +ms` 等**细粒度打印本身耗时**（`_ms` 字符串 fprintf 很贵，一度让盘面更卡），已完成并**移除**，保留原有 `SG_REDRAW_TIMER`/`SG_CTX_TICK_TRACE` 等开关。

### 19.6 save/load 验证与 MCP 接口对齐（commit `cd9c4e7`）
- **探针**：`clannad_ctl --verify-sl --save-at-frame N --slot S` 做保存→跳走→读回的往返。
- **修复的坑**：`menu_save_slot`/`menu_load_slot` 只是**排队** `RuntimeSaveRequest`，实际执行靠 VM 在 `CD_COMMAND` 里 `drain_runtime_save_load_requests()`。原先 clannad_ctl 直接调这两个函数而不让 VM drain，故 load 永远拿到跳转后场景 → `ok:false`。**修复**：
  - 新增 `SceneVm::drain_save_load_requests()`（宿主/ctl/MCP 可直接执行排队请求）与 `CommandContext::has_pending_runtime_save_load()`；
  - 把 `sync_save_slots_from_disk` 暴露为 `CommandContext` 的公开方法，以便可靠刷新/读取存档数量。
- **读档判定**：load 有效性以 **scene + 对话文本一致** 为准（`text_match`）；`current_line_no` 在 load 后会因从存档点恢复而差几行，非 bug。
- **验证结果**：`--verify-sl` 往返 `ok:true text_match:true`，`saved_line=55 loaded_line=51`（line 差属恢复起点行号，文本一致）；存档文件 `savedata/0003.sav` 成功写盘。
- **MCP 读档接口**：`emit_status` 现在上报 `save_count`（最大槽位数，CLANNAD 默认 100）+ `save_used`（非空槽位数）+ 每槽 `exist/title/msg`，读档工具可直接枚举存档数量与各槽状态。

### 19.7 方案 A：引擎内部自动进入游戏（`--auto-start`，commit 本会话）
- **目标**：让引擎启动后自动走“标题 → New Game → 第一行对话”，MCP 一启动即可读取剧情状态，无需手动点击。
- **实现**：`siglus_engine.rs` 加 `--auto-start`/`SG_AUTOSTART` + `AutoStartPhase` 状态机（Wait → TitleAdvance → ClickNewGame → StoryStarted → Failed），在 `redraw` 里每帧 `auto_step()`：
  - **Wait**：等 ~90 帧让引擎初始化；
  - **TitleAdvance**：在系统/标题场景注入 **Enter**（`on_key_down/up(Enter)`），直到 `_system_title` 稳定；
  - **ClickNewGame**：注入**游戏坐标**鼠标点击（`on_mouse_move/down/up` 分帧），候选扫描按钮中心；
  - **StoryStarted**：检测到 `seen*` 场景且 `line>0`（第一行对话）→ 停止，MCP 接管。
- **已验证**：✅ 引擎能自动驱动到 `_system_title`（Enter 进标题稳定）；`SG_AUTOSTART_TRACE` 显示注入的候选坐标。
- **已知边界（诚实说明）**：New Game 按钮点击这一环，**引擎内部注入的 `on_mouse_move/down/up` 无法稳定命中标题按钮** —— 因为 CLANNAD 标题按钮命中测试依赖**渲染出的精灵像素 alpha**（`hit_test_render_sprite`），注入点击与渲染精灵的时序/坐标在无头自动环境下不匹配。而**手动/窗口自动化点击（已验证 `post_newgame.ps1` / `map_menu2.ps1`）能进**。
- **结论**：方案 A 的“全自动进入到第一行”目前受限于引擎按钮命中机制，**New Game 这一步最稳的是窗口自动化（`PostMessage` 点击窗口坐标）或手动点击**，而非纯引擎内注入。已驱动的 Title→标题画面可复用；若要走通全自动，需让引擎在渲染后构建精灵时机点注入，或改用窗口自动化点击 New Game（坐标需窗口缩放映射）。
- **建议**：MCP 后台用 `--auto-start` 驱动到标题 + 一次窗口自动化点击 New Game 进剧情；或先让 agent 通过 `STATE` 读到 `_system_title`，再由 agent 决定。

## 阶段 5（可选，未定）：headless 深推
- 无头深推受 §16.2 `_cl_forclannad` 缺口限制，暂以窗口形态为准（§0 D2）。

---

## 19.8 MCP Server + 实时桥（plan-B）落成 + 确认 choose 引擎缺口（本会话 2026-09-08）

### 已交付（提交 `siglus_rs@a3eb708`，mcp_server 已于 `16a996e` 等落库）
- **MCP Server（Python, mcp 2.2.0 v2 `MCPServer`，10 工具）**：
  - 读：`get_status` / `get_dialogue` / `get_choices` / `get_save_list`
  - 控制：`advance` / `choose` / `skip_to_choice` / `save` / `load` / `jump`
  - 桥：`src/mcp_server/bridge.py`（TCP 客户端，轮询 STATE 直到动作生效返回**执行后**状态）；引擎 `--bridge`（或 `CLANNAD_BRIDGE=1`）开本地 TCP 端口，一条命令一连接。
- **引擎 control/state 修复**：
  - `ctx_state_json`：新增 `halted`、`save_count`、`save_used`、`save_slots`(占用槽)；**选项改读 `selbtn.choices`**（CLANNAD `$mes_sel` 真选项），回退 `btnselitem_lists`。
  - `advance`：不再是单次 Enter（只揭示不推进），改为**逐帧 pump `run_script_proc`/`tick_frame` 直到文本/行变化**。
  - `choose`：新增 `CommandContext::choose_selbtn()` 直接走 `finish_selbtn`（镜像鼠标 decide 路径），而非仅设 pending result。
  - `skip`：把收集的对话段作为 `skip_lines` 写入 bridge 状态（`skip()` 返回整段 + 到达选项时的状态）。
  - `load`：读档后注入合成鼠标移动 + Enter 并 pump 几帧，使恢复的对话框**无需用户 hover 即出现**（修复“load 要 hover”）。
  - `save_dir`：优先 `savedata_zh`（Steam 简中版存档目录），回退 `savedata`；`file.rs`/`stage.rs` 读路径也加 `savedata_zh` 候选。
  - 启动时 `sync_save_slots_from_disk`，MCP 立即读到真实存档数。
  - `on_mouse_wheel`：**选项列表非空时拦截滚轮推进默认项**（修复“滚轮自动选第一个”）。
- **方案 A auto-start（§19.7 基础上）**：New Game 按钮改为**先 hover 轮询命中（`newgame_hit`）再同帧 move→down→up**；第一行对话判定改为 `scene 是 seen* 且消息窗口有文本`（不再只 `line>0`）；标题稳定后停止 Enter、过 `_system_adv`/`_system_start` 后继续 Enter 推进到剧情。实测 3/3 稳定到 `seen6900:17`（约 29s）。

### ✅ 已验证通过
- `save`/`save_slots` 检测：`get_status` 报 `save_count=100 save_used=2 save_slots=[0,1]`（此前 0，因读了错误目录）。
- `advance` 稳定推进行号；`load` 后对话框自动出现；`skip` 返回 `skip_lines` 整段；`get_status().choices` 正常返回真实选项。
- MCP Server stdio：`tools/list` 10 工具；MCP Inspector 可加载（`from mcp_server.bridge import` 绝对导入修复 `mcp dev` 单文件加载问题）。

### ⚠️ 未解决/确认的引擎缺口（本会话确认为**非 off-by-one**，是 §16.2 真实缺口）
- **`choose()` 无论手动还是 MCP，都进第一项**。SG_SELBTN_TRACE 决定性证据：
  - 手动选第 2 项：`deliver result=1 choices=2 cursor=1`；`choose(1)`：`deliver result=1`；两条路径 result 都正确指向第 2 项，**但脚本仍进第一项**。
  - `ctx_return` trace：`$mes_sel` 结果**不走 `take_ctx_return` 常规命令返回栈**；选择后进入 `_cl_forclannad` 场景，其 `include-call` 返回 `246`/`-1`（choice→分支 分发），而这些值不被正确应用。
- **根因 = §16.2 `_cl_forclannad` include-call 缺口**：`ASSIGN` 的 STR 实参未入栈 → `str stack underflow`；`assign_call_prop_result` 对 include-call 参数 form=20 `sub=[0]` 不支持。CLANNAD `$mes_sel` 的选择结果经 `_cl_forclannad` 分发，此缺口导致**所有选项都走默认/第一条分支**。**这不是 off-by-one（已排除：result=1 正确仍进第一项），而是引擎 include-call 实参传递缺陷**。
- AGENT.md §16.2 已记：真正修法是**实现 include-call（`cur_call.*` / `CALL.L/K` / `__elm` 参数）的字符串实参传递与 form=20 赋值**，属中等以上引擎工作量。
- （另：load 回开头再 skip 偶发卡死/停在 `_system_language`，同属深推/runtime 状态残留，优先级低于 `_cl_forclannad`。）

### 下一步目标（主）
1. **修复 §16.2 `_cl_forclannad` include-call 字符串实参传递 + form=20 赋值** → 让 CLANNAD 选择分发真正生效 → 手动/`choose()` 能选不同分支 → **游戏可正常游玩分支**。
   - 入口：`_cl_forclannad` 场景、`$mes_sel` 后的 include-call（`cur_call.*`/`CALL.L/K`/`__elm`）、`assign_call_prop_result` 对 form=20 的处理。
   - 验证：走到真实选择点，`get_choices` 返回多选项，`choose(i)` 进第 i 项分支；`manual` 选第 2 项进第 2 项。
2. （次要）深推/load-back 后 skip 的 runtime 残留卡死。

### 状态
- 已提交：`siglus_rs@a3eb708`（引擎/桥/control+state 修复）；`mcp_server` 已落库（16a996e 等）。
- 未提交：本根仓库 submodule 指针（待 `git add siglus_rs` 提交 `AGENT.md` 与指针）。
- **可玩性阻塞**：`_cl_forclannad` 缺口 → `choose` 不可用 → 分支无法按选择进入。修复它是主线，已定位未实现。

---

## 19.9 推进 `_cl_forclannad` include-call 修复（本会话 2026-09-08）

### 定位（与 §16.2/§19.8 一致）
- CLANNAD `$mes_sel` 选择结果经 `_cl_forclannad` 场景的 include-call 分发（读 `cur_call.l[0]`/CALL_PROP 选分支）。
- 分发时，include-call 的**标量 CALL_PROP 赋值**会以 **`form=20`（FM_STR）/ `form=10`（FM_INT）带一个孤立尾部下标 `sub=[0]`** 的形式出现 → `assign_call_prop_result` 只处理 `sub` 为空，落进 `_ => bail!("unsupported call prop assign form=20 sub=[0]")` → include-call 中止 → 分支分发结果（`246`/`-1`）不生效 → **所有选项都走默认/第一条分支**。

### 修复（`crates/siglus_scene_vm/src/vm.rs`）
- 新增 `SceneVm::is_lone_scalar_sub(sub)`：`sub.len()==1 && sub[0] >= 0`（单元素、非负、非 `ELM_ARRAY` 下标链）。
- `assign_call_prop_result` 的 `FM_INT`/`FM_STR` 分支条件放宽为 `sub.is_empty() || Self::is_lone_scalar_sub(sub)`：对**标量** CALL_PROP 的孤立下标，按整值写入（原引擎即写整值；把它当真实槽位下标会让标量自身存储悬空）。真正的列表下标（`[ELM_ARRAY, idx]`）仍走原有分支/上报，不回退。
- **说明**：只消掉"form=20 sub=[0] unsupported"这一个 bail，让 include-call 能完成标量赋值。§16.2 里另一个 `str stack underflow`（字符串实参未入栈）属独立的 include-call 字符串实参传递问题，本改动不掩盖也不覆盖它 —— 需单独立项（本会话调查：窗口态游玩、对话显示均正常，未复现该 underflow）。

### 验证
- 新增单元测试 `call_property_reference_tests::scalar_{str,int}_call_prop_accepts_lone_index_sub`：
  - FM_STR + `sub=[0]` + `Value::Str` → 整值写入 ✅
  - FM_INT + `sub=[0]` + `Value::Int` → 整值写入 ✅
  - FM_STR + `sub=[ELM_ARRAY,0]`（真实列表下标）→ 仍 bail ✅
  - `cargo test -p siglus_scene_vm --lib call_prop_accepts_lone_index_sub` → **2 passed**。
- `cargo build -p siglus_scene_vm --bin clannad_ctl` ✅；`--bin siglus_engine` ✅（均"Finished"，无 error；stderr 的 `[exit code:1]` 是 PowerShell `Select-Object` 管道假象）。
- **端到端（选择点 choose(i) 进第 i 项分支）尚未在本会话跑通**：headless 驱动从 seen0414 到选择点极慢（intro→line248 已到 frame≈6060，仍未见选项），且受 §19.8"choose 结果经 `_cl_forclannad` 分发"限制；该闭环需按 §19.8 用**窗口态引擎 + `skip`/MCP** 验证（`SG_CTL=SKIP:..@<frame>` 到选择点 → `choose(i)` → 观察分支 scene/line 是否随 i 变化）。

### 下一步
1. 用窗口态引擎（或给 clannad_ctl 加 skip+`choose_selbtn(i)`）跑到真实选择点，验证 `choose(0)` 与 `choose(1)` 进入不同分支。
2. 独立跟踪 §16.2 的 `str stack underflow`（include-call 字符串实参传递）—— 若它也在选择点触发，将一并处理；当前未在对话显示路径复现。
3. 提交 `siglus_rs` 改动 + 更新本根仓库 submodule 指针与 `AGENT.md`。