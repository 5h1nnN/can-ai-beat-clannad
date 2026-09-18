# CLANNAD MCP

让 AI agent 直接玩 CLANNAD（Steam 中文版）。

由两部分组成：

| 部分 | 是什么 | 位置 |
|---|---|---|
| **引擎** `siglus_engine.exe` | 适配CLANNAD Steam的SiglusEngine （修改自[xmoezzz/siglus_rs](https://github.com/xmoezzz/siglus_rs)） | `siglus_rs/`（产物 `target/release/siglus_engine.exe`） |
| **MCP 服务** `clannad-mcp` | stdio MCP server，把桥封装成 MCP 工具（`advance` / `choose` / `skip_to_choice` …） | `mcp_server/`（Python 包） |

> 本项目**不包含任何游戏资源**。你必须有 CLANNAD Steam 中文版。

---

## 1. 前置条件

- Windows 10/11（引擎是窗口程序，用 DirectX/GPU 正常渲染）
- 正版 CLANNAD（Steam 中文版）已安装，例如 `E:\SteamLibrary\steamapps\common\CLANNAD`
- 跑 MCP 服务需要 Python ≥ 3.12；推荐装 [uv](https://docs.astral.sh/uv/)（`winget install astral-sh.uv` 或官方脚本）
- 只有在你想自己编译引擎时才需要 Rust 工具链（普通用户直接下载 `siglus_engine.exe` 即可）

---

## 2. 快速开始（3 步）

#### 第 0 步：准备游戏

1. 打开CLANNAD Steam版游戏目录，备份存档（直接修改`SAVEDATA/`和`savedata_zh/`文件夹名称，使得游戏回到初始状态）
2. 将`endings_map.toml`放在游戏目录下（用于结局判定）

#### 第 1 步：下载引擎

方式 A（推荐，普通用户）：下载 Release 里的 `siglus_engine.exe`，放进任意目录。

方式 B（自行编译）：

```powershell
cd siglus_rs
cargo build --release -p siglus_scene_vm
# 产物：
#   target\release\siglus_engine.exe   ← 引擎（必需）
#   target\release\clannad_ctl.exe      ← 无窗口跑脚本/调试（可选）
#   target\release\clannad_text.exe     ← 校验判定句、列场景对白（可选，见 §6）
#   target\release\clannad_probe.exe    ← 场景探针（可选）
```

#### 第 2 步：启动引擎

把仓库里的 `run_engine.cmd` 放到 `siglus_engine.exe` 旁边，将开头的 `GAME_DIR`改为自己的CLANNAD Steam版游戏目录：

```bat
set "GAME_DIR=path\to\CLANNAD"
```

然后双击运行（端口文件、语言、快进预算都设好了）。它等价于：

```powershell
$env:CLANNAD_BRIDGE_PORT_FILE = "$env:TEMP\clannad_bridge.port"
$env:SIGLUS_LANGUAGE = "ZH"
.\siglus_engine.exe --project-dir "E:\SteamLibrary\steamapps\common\CLANNAD" --bridge --auto-start
```

- `--bridge`：开启控制桥（MCP 必需）
- `--auto-start`：自动从标题进 New Game 到第一句（省得手动点）
- 引擎窗口必须保持开着（关掉窗口 = 退出）。可以把窗口最小化；不要用任务管理器结束它。

> 不用 `run_engine.cmd`、自己手敲命令也可以，那就照上面三行设好环境变量（建议始终给 `CLANNAD_BRIDGE_PORT_FILE` 一个绝对路径）。

#### 第 3 步：安装 MCP 服务

先装：

```powershell
uvx clannad-mcp --help          # 直接跑（首次会自动下载）
# 或常驻安装：
uv tool install clannad-mcp     # 之后命令名就是 clannad-mcp
```

然后在 MCP 宿主（Claude Desktop / 其它支持 MCP 的客户端）的配置里加：

```json
{
  "mcpServers": {
    "clannad": {
      "command": "uvx",
      "args": ["clannad-mcp"]
    }
  }
}
```

即可。只有你想把端口文件放到别处时，才需要两边同时指定：

```json
{
  "mcpServers": {
    "clannad": {
      "command": "uvx",
      "args": ["clannad-mcp"],
      "env": {
        "CLANNAD_BRIDGE_PORT_FILE": "path\\to\\clannad_bridge.port"
      }
    }
  }
}
```

（放别处的话，`run_engine.cmd` 里的 `CLANNAD_BRIDGE_PORT_FILE` 也要改成同一个值。）

不用 `uvx` 也可以（从源码/本地 venv 跑）：

```json
{
  "mcpServers": {
    "clannad": {
      "command": "E:\\7_projects\\clannad_mcp\\mcp_server\\.venv\\Scripts\\python.exe",
      "args": ["-m", "mcp_server.clannad_mcp"],
      "env": {
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
| `save(slot)` / `load(slot)` | 存/读档（槽位与游戏内一致，会覆盖该槽） |
| `jump(scene)` | 直接跳到某场景（调试/回退用） |
| `get_save_list` | 槽位上限与已占用槽 |
| `get_recovered` | 引擎容错的脚本错误站点清单（排查用） |

`skip_to_choice` 返回里最常用的字段：

- `skip_lines`：本次快进收集到的全部对白（逐行含 `bgm_changed` / `background_changed`）
- `skip_stop_reason`：为什么停 —— `choice`（到选项）/ `ending`（命中判定句）/ `halted`（剧情结束或异常停机）/ `time_budget`、`step_budget`（预算用尽）/ `requested`（客户端要求停）
- `skip_timeout`：`true` 表示"预算用尽被停"；此时可直接再调一次 `skip_to_choice` 接着快进
- `date` / `skip_dates`：游戏内日期变化及其确切行号
- `ending` / `skip_endings`：命中的结局（名字 + 判定句）及其确切行号

---

## 4. 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `CLANNAD_BRIDGE_PORT_FILE` | 控制桥端口文件；引擎与 MCP 必须一致 | 两边默认都是 `%TEMP%\clannad_bridge.port`（用 `run_engine.cmd` 启动引擎时；手敲命令启动引擎时它写在引擎的工作目录） |
| `SIGLUS_LANGUAGE` | 文本语言（中文版用 `ZH`） | 自动 |
| `CLANNAD_SKIP_BUDGET_MS` | 单次快进的墙钟预算（毫秒）；引擎到点自停 | `40000` |
| `CLANNAD_SKIP_TIMEOUT` | MCP 侧兜底等待（秒），只用于引擎无响应的异常情况；必须小于 MCP 宿主自身的超时 | `45` |
| `CLANNAD_ENDINGS_MAP` | 判定句表路径 | `<GAME_DIR>\endings_map.toml` |
| `SIGLUS_VM_STRICT=1` | 脚本错误不再容错，遇到就停机（排查引擎 bug 用） | 关 |
| `SG_SKIP_TRACE=1` | 把快进决策写进 `skip_trace.log`（排查快进问题用） | 关 |

---

## 5. 已知限制

在有选择枝的下一句存档后读档可能读出一个"推不动"的状态，这是当前引擎的一个遗留问题

---

## 6. 许可与免责

- 本项目以 **Mozilla Public License 2.0（MPL-2.0）** 发布，全文见 [`LICENSE`](LICENSE)
- 项目地址：<https://github.com/5h1nnN/can-ai-beat-clannad>
- 本项目不附带 CLANNAD 的任何游戏数据
- 引擎fork自[xmoezzz/siglus_rs](https://github.com/xmoezzz/siglus_rs)，本项目的引擎子仓库：<https://github.com/5h1nnN/siglus_rs>

---

## 7. 发布（PyPI）

```powershell
cd mcp_server
uv build     # 产出 dist\clannad_mcp-0.1.0-py3-none-any.whl 与 .tar.gz（内含 LICENSE）
uv publish   # 需要 PyPI API token：uv publish --token pypi-xxxx，或设环境变量 UV_PUBLISH_TOKEN
```

- 想先在测试库验证：`uv publish --publish-url https://test.pypi.org/legacy/`
- 用户安装：`uvx clannad-mcp`（或 `uv tool install clannad-mcp` / `pipx install clannad-mcp`）
- 包元数据（名称/版本/许可证/项目地址/入口点）都在 `mcp_server/pyproject.toml`
