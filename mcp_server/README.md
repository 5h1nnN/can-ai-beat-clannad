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
2. 引擎与 MCP 使用**同一个**端口文件路径：
   `CLANNAD_BRIDGE_PORT_FILE`（引擎写端口，MCP 读端口）

## MCP 宿主配置示例

```json
{
  "mcpServers": {
    "clannad": {
      "command": "uvx",
      "args": ["clannad-mcp"],
      "env": {
        "CLANNAD_BRIDGE_PORT_FILE": "C:\\Users\\<你>\\AppData\\Local\\Temp\\clannad_bridge.port"
      }
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
| `CLANNAD_BRIDGE_PORT_FILE` | 端口文件路径，必须与引擎一致 | 若干候选路径（含当前目录的 `clannad_bridge.port`） |
| `CLANNAD_SKIP_TIMEOUT` | `skip_to_choice` 的兜底等待秒数；须小于 MCP 宿主超时 | `45` |
