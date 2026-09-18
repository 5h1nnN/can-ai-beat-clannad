# clannad-mcp

MCP (stdio) server that drives the **CLANNAD** engine (`siglus_engine.exe`, the Rust
reimplementation in `../siglus_rs`) over its local TCP control bridge.

完整安装/运行/发布说明见仓库根目录的 [`../README.md`](../README.md)。要点：

## 安装

```powershell
uvx clannad-mcp                 # 不安装，直接运行
uv tool install clannad-mcp     # 常驻安装（命令：clannad-mcp）
```

## 使用前提

1. 引擎已在跑，并开了控制桥：
   `siglus_engine.exe --project-dir "<GAME_DIR>" --bridge --auto-start`
   （仓库根的 `run_engine.cmd` 就是干这个的，只需改里面的 `GAME_DIR`）
2. 端口文件两端一致 —— **默认已经一致**：引擎（经 `run_engine.cmd`）写
   `%TEMP%\clannad_bridge.port`，本客户端也默认读这个文件，所以通常**不需要配任何环境变量**。

## MCP 宿主配置示例

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

## 工具

`get_status` · `get_dialogue` · `get_choices` · `advance` · `choose` ·
`skip_to_choice` · `save` · `load` · `jump` · `get_save_list` · `get_recovered`

## 目录

```
src/mcp_server/
  clannad_mcp.py   # MCP 工具定义（stdio server）
  bridge.py        # 控制桥客户端（一行命令 -> 一行 JSON 状态）
```

## 环境变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `CLANNAD_BRIDGE_PORT_FILE` | 端口文件路径；想放到别处时两端都要设成同一个值 | `%TEMP%\clannad_bridge.port`（另会探测检出目录、当前目录及其父目录下的 `clannad_bridge.port`） |
| `CLANNAD_SKIP_TIMEOUT` | `skip_to_choice` 的兜底等待秒数；须小于 MCP 宿主超时 | `45` |

## 许可

Mozilla Public License 2.0（MPL-2.0），全文见 [`LICENSE`](LICENSE)。
项目地址：<https://github.com/5h1nnN/can-ai-beat-clannad>

## 发布

```powershell
uv build     # dist\clannad_mcp-0.1.0-py3-none-any.whl / .tar.gz（含 LICENSE）
uv publish   # 需要 PyPI token：--token pypi-xxxx 或 UV_PUBLISH_TOKEN
```
