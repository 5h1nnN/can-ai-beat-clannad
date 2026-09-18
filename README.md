# CLANNAD MCP

让 AI agent 直接玩 CLANNAD（Steam 中文版）：读状态、推进对白、选选项、存读档、快进，并且能按**文本判定句**识别 TRUE END / 坏结局。

由两部分组成：

| 部分 | 是什么 | 位置 |
|---|---|---|
| **引擎** `siglus_engine.exe` | SiglusEngine 的 Rust 重写，真正跑游戏（窗口里就是你熟悉的 CLANNAD），并开一个本地 TCP 控制桥 | `siglus_rs/`（产物 `target/release/siglus_engine.exe`） |
| **MCP 服务** `clannad-mcp` | stdio MCP server，把桥封装成 MCP 工具（`advance` / `choose` / `skip_to_choice` …） | `mcp_server/`（Python 包） |

> 本项目**不包含任何游戏资源**。你需要自备正版 CLANNAD（Steam 中文版），引擎只读取你自己安装目录里的 `Scene.pck`、`dat/`、`g00/`、`savedata_zh/` 等文件。

---

## 1. 前置条件

- **Windows 10/11**（引擎是窗口程序，用 DirectX/GPU 正常渲染）
- **正版 CLANNAD**（Steam 中文版）已安装，例如 `E:\SteamLibrary\steamapps\common\CLANNAD`
- 跑 MCP 服务需要 **Python ≥ 3.12**；推荐装 [uv](https://docs.astral.sh/uv/)（`winget install astral-sh.uv` 或官方脚本）
- **只有在你想自己编译引擎时才需要 Rust 工具链**（普通用户直接下载 `siglus_engine.exe` 即可）

---

## 2. 快速开始（3 步）

### 第 1 步：拿到引擎

**方式 A（推荐，普通用户）**：下载 Release 里的 `siglus_engine.exe`，放进任意目录（例如 `D:\clannad-mcp\`）。

**方式 B（自行编译）**：

```powershell
cd siglus_rs
cargo build --release -p siglus_scene_vm
# 产物：
#   target\release\siglus_engine.exe   ← 引擎（必需）
#   target\release\clannad_ctl.exe      ← 无窗口跑脚本/调试（可选）
#   target\release\clannad_text.exe     ← 校验判定句、列场景对白（可选，见 §6）
#   target\release\clannad_probe.exe    ← 场景探针（可选）
```

### 第 2 步：启动引擎

把仓库里的 **`run_engine.cmd`** 放到 `siglus_engine.exe` 旁边，改开头两处路径，然后双击运行：

```bat
set "GAME_DIR=E:\SteamLibrary\steamapps\common\CLANNAD"
set "CLANNAD_BRIDGE_PORT_FILE=%TEMP%\clannad_bridge.port"
```

它等价于：

```powershell
$env:CLANNAD_BRIDGE_PORT_FILE = "$env:TEMP\clannad_bridge.port"
$env:SIGLUS_LANGUAGE = "ZH"
.\siglus_engine.exe --project-dir "E:\SteamLibrary\steamapps\common\CLANNAD" --bridge --auto-start
```

- `--bridge`：开启控制桥（MCP 必需）
- `--auto-start`：自动从标题进 New Game 到第一句（省得手动点）
- **引擎窗口必须保持开着**（关掉窗口 = 退出）。可以把窗口最小化；不要用任务管理器结束它。

### 第 3 步：把 MCP 服务接到你的 AI 客户端

先装：

```powershell
uvx clannad-mcp --help          # 直接跑（首次会自动下载；必须能被 MCP 宿主调用）
# 或常驻安装：
uv tool install clannad-mcp     # 之后命令名就是 clannad-mcp
```

然后在 MCP 宿主（Claude Desktop / 其它支持 MCP 的客户端）的配置里加：

```json
{
  "mcpServers": {
    "clannad": {
      "command": "uvx",
      "args": ["clannad-mcp"],
      "env": {
        "CLANNAD_BRIDGE_PORT_FILE": "C:\\Users\\<你的用户名>\\AppData\\Local\\Temp\\clannad_bridge.port"
      }
    }
  }
}
```

**关键点：`CLANNAD_BRIDGE_PORT_FILE` 两边必须一致**（引擎写、MCP 读）。不设的话客户端只能碰运气去当前目录找 `clannad_bridge.port`。

不想用 `uvx` 也可以（从源码/本地 venv 跑）：

```json
{
  "mcpServers": {
    "clannad": {
      "command": "E:\\7_projects\\clannad_mcp\\mcp_server\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server.clannad_mcp"],
      "env": {
        "CLANNAD_BRIDGE_PORT_FILE": "C:\\Users\\<你的用户名>\\AppData\\Local\\Temp\\clannad_bridge.port",
        "PYTHONPATH": "E:\\7_projects\\clannad_mcp\\mcp_server\\src"
      }
    }
  }
}
```

---

## 3. 工具一览

| 工具 | 用途 |
|---|---|
| `get_status` | 当前位置（场景/行号/是否阻塞/存档槽…），决策前先看它 |
| `get_dialogue` | 当前说话人 + 对白文本 + 是否有选项 |
| `get_choices` | 当前选项列表（`choose` 的下标就是它的下标，0 起） |
| `advance` | 推进一句（注一次 Enter）；命中结局判定句时返回 `ending` |
| `choose(idx)` | 在选项处选第 `idx` 项 |
| `skip_to_choice` | 快进：可跨多天、按行标注日期与结局；到选项/结局/预算停下 |
| `save(slot)` / `load(slot)` | 存/读档（槽位与游戏内一致，**会覆盖**该槽） |
| `jump(scene)` | 直接跳到某场景（调试/回退用） |
| `get_save_list` | 槽位上限与已占用槽 |
| `get_recovered` | 引擎容错的脚本错误站点清单（排查用） |

`skip_to_choice` 返回里最常用的字段：

- `skip_lines`：本次快进收集到的全部对白（逐行含 `bgm_changed` / `background_changed`）
- `skip_stop_reason`：为什么停 —— `choice`（到选项）/ `ending`（命中判定句）/ `halted`（剧情结束或异常停机）/ `time_budget`、`step_budget`（预算用尽）/ `requested`（客户端要求停）
- `skip_timeout`：`true` 表示"预算用尽被停"（**不是**到达）；此时可直接再调一次 `skip_to_choice` 接着快进
- `date` / `skip_dates`：游戏内日期变化及其**确切行号**
- `ending` / `skip_endings`：命中的结局（名字 + 判定句）及其**确切行号**

---

## 4. 结局判定（`endings_map.toml`）

在**游戏安装目录**放一份 `endings_map.toml`（引擎启动时自动读，也可用 `CLANNAD_ENDINGS_MAP` 指定别的路径）：

```toml
[endings]
@"请和风子交往吧！" = "风子 Fuko TRUE END"
@"有人放在我的枕边。" = "风子 Fuko BAD END"
"某个不一定在整行开头的关键句" = "示例：子串匹配"
```

规则：

- 左边 = **判定句**，右边 = 上报的结局名（中文随便写）
- `@` 前缀 = **整行精确匹配**（推荐）；不加 `@` 则是**子串匹配**
- 引擎每帧拿"对话窗当前文字"去比，比对前会**剥掉** `「」『』“”"'` 这层框 —— 所以判定句里**不要写 `「」`**
- 同一句命中只上报一次（每局去重，重新 load/jump 后重新计）
- 命中后：`advance` 在返回里带 `ending`；`skip_to_choice` 会**停在那句**（`skip_stop_reason="ending"`），并在 `skip_lines[i].ending` 上标出确切行

**写完一定要校验**（判定句必须与"实际显示的那一整行"一致，差一个标点就不会命中）：

```powershell
# 把判定句逐行写进一个 UTF-8(无 BOM) 文本文件 phrases.txt，然后：
.\clannad_text.exe --dat "<GAME_DIR>\dat" --search-file phrases.txt
# 输出的每一行 {db,row,serial,jp,zh} 就是库里命中的那一行：
#   - 没有任何输出 => 这句在游戏里不存在（写错了）
#   - zh 剥掉「」后与判定句完全相等 => 可安全使用 @ 精确匹配
```

---

## 5. 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `CLANNAD_BRIDGE_PORT_FILE` | 控制桥端口文件；**引擎与 MCP 必须一致** | 引擎：进程当前目录下 `clannad_bridge.port` |
| `SIGLUS_LANGUAGE` | 文本语言（中文版用 `ZH`） | 自动 |
| `CLANNAD_SKIP_BUDGET_MS` | 单次快进的墙钟预算（毫秒）；引擎到点自停 | `40000` |
| `CLANNAD_SKIP_TIMEOUT` | MCP 侧兜底等待（秒），只用于引擎无响应的异常情况；**必须小于 MCP 宿主自身的超时** | `45` |
| `CLANNAD_ENDINGS_MAP` | 判定句表路径 | `<GAME_DIR>\endings_map.toml` |
| `SIGLUS_VM_STRICT=1` | 脚本错误不再容错，遇到就停机（排查引擎 bug 用） | 关 |
| `SG_SKIP_TRACE=1` | 把快进决策写进 `skip_trace.log`（排查快进问题用） | 关 |

---

## 6. 存档

- 游戏的存档在 `<GAME_DIR>\savedata_zh\`：`0001.sav` = 槽 1，`global.sav` = 全局进度/光玉等
- MCP 的 `save(slot)` / `load(slot)` 用的槽号与游戏内一致，**save 会覆盖已有存档**，建议先备份 `savedata_zh\`
- 引擎自己会更新 `read.sav`（回放/已读），这是正常的

---

## 7. 故障排查（都是实际踩过的坑）

| 现象 | 原因 / 处理 |
|---|---|
| MCP 报 "engine didn't write a port file within 30s" | 引擎没在跑，或两边 `CLANNAD_BRIDGE_PORT_FILE` 不一致，或路径写错（用绝对路径） |
| `skip_to_choice` 很久才返回 / 调用方超时 | 引擎预算 `CLANNAD_SKIP_BUDGET_MS` 必须**明显小于** MCP 宿主的超时；宿主超时 60s 时用默认 40s 即可 |
| `skip` 返回 0 行、`skip_timeout=true` | 到了推不动的画面（标题/系统菜单只认鼠标点击）。用 `advance` / `load` / `jump`，不要在菜单上快进 |
| 同一判定句每次 skip 都停在同一句 | 目前判定句是"每次都停"。用一次 `advance` 过去，或干脆不把它当必停点 |
| 在选项画面上存了档，读回来推不动 | **已知限制**：不要在选项表还在屏幕上时存档（点完选项后等选项消失，约 1 秒）。若已经存了，换用更早的存档 |
| `halted: true` 且 `skip_stop_reason="halted"` | 剧情脚本走到尽头（坏结局/结局后）或引擎真出问题；配合 `get_recovered` 看是否被容错过。要在结尾也能收到信号，就在判定句表里加那句 |
| 想确认引擎版本 | 引擎启动会在当前目录写 `engine_state.log`，首行 `[BUILD]` 带 exe 路径 / 大小 / mtime / pid；另外启动日志里有 `[engine] loaded N ending phrase(s)` |

---

## 8. 构建与发布

### 引擎（Windows 单文件）

```powershell
cd siglus_rs
cargo build --release -p siglus_scene_vm
```

发布建议：

- 只发 `siglus_engine.exe`（约 59 MB，单文件、无需运行时）；可选带 `clannad_ctl.exe` / `clannad_text.exe`
- 一起打包：本 `README.md`、`run_engine.cmd`、`endings_map.toml` 样例
- 版本标识：exe 的 `size`/`mtime` 会写进 `engine_state.log` 的 `[BUILD]` 行，用户报障时让他附上这一行即可
- 建议同时给 `SHA256` 校验值
- **不要**把游戏资源打进包里

### MCP 服务（PyPI）

```powershell
cd mcp_server
uv build                 # dist\clannad_mcp-0.1.0-py3-none-any.whl + .tar.gz
uv publish --publish-url https://test.pypi.org/legacy/   # 先发 TestPyPI 验证
uv publish                                                # 正式 PyPI
```

发布前请补：`pyproject.toml` 的 `license`、项目主页/仓库 URL，以及仓库根的 `LICENSE` 文件（当前未指定许可证）。

用户侧安装：

```powershell
uvx clannad-mcp                     # 临时运行
uv tool install clannad-mcp         # 常驻（命令 clannad-mcp）
pipx install clannad-mcp            # 等价
```

### 版本兼容

MCP 服务依赖引擎桥返回的 `skip_seq`、`ending`、`skip_endings`、`date` 等字段（对应引擎提交 **≥ 7562e7d**）。旧引擎不会报错，只是缺少这些字段（客户端会容错降级）。发版时请把"引擎版本 ↔ MCP 版本"对应关系写进 Release 说明。

---

## 9. 已知限制

1. 选项画面上的存档可能读出一个"推不动"的状态（见 §7），这是当前引擎的一个遗留问题
2. 判定句每次 `skip` 都会停在同一句（没有"一局只停一次"）
3. 标题/系统菜单上的 `skip` 会空转到预算（返回 0 行）
4. 坏结局本身只有 `halted: true`；要拿到名字就在 `endings_map.toml` 里加判定句

---

## 10. 许可与免责

- 本项目**不附带 CLANNAD 的任何游戏数据**；请自备正版，并遵守其许可
- 引擎是社区重写实现，与 Key / VisualArts / Sekai Project 无任何关联
- 使用本工具产生的存档风险自负（`save` 会覆盖槽位，建议先备份 `savedata_zh\`）
