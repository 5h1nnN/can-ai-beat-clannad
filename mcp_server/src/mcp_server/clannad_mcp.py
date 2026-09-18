"""
MCP Server for CLANNAD (Steam CN) — real-time control over the plan-B TCP bridge.

The engine (siglus_engine.exe) must be running in a window with:
    CLANNAD_BRIDGE=1
    CLANNAD_BRIDGE_PORT_FILE=<path matching bridge.PORT_FILE>

The session is continuous (the engine keeps running and rendering), so the model
"plays" CLANNAD live instead of restarting headlessly each call.

"""
from __future__ import annotations

from mcp.server import MCPServer

from mcp_server.bridge import get_bridge

mcp = MCPServer(
    "clannad-mcp",
    instructions=(
        "CLANNAD（Steam中文版）实时控制。先 get_status / get_dialogue 看当前所在；"
        "需要推进时用 advance/skip_to_choice；出现选项时 get_choices 读然后用 choose 选择；"
        "需要回退/做分支时用 save/load。"
    ),
)


def _snapshot() -> dict:
    return get_bridge().state()


@mcp.tool()
def get_status() -> dict:
    """读取当前状态：场景名、场景号、行号、是否阻塞/等待、存档槽数。

    这是"read 类"主入口，agent 每轮决策前先看它确认位置。
    若刚刚命中结局判定句，返回里还会带 `ending`。
    """
    return _snapshot()


@mcp.tool()
def get_dialogue() -> dict:
    """读取当前对话：说话人(name)、对白文本(text)、是否已到选择点。

    返回 {name, text, choices};choices 非空表示正在等待选择。
    """
    st = _snapshot()
    return {
        "name": st.get("name", ""),
        "text": st.get("text", ""),
        "choices": st.get("choices", []),
    }


@mcp.tool()
def get_choices() -> list[str]:
    """读取当前选项列表（每一项为选项文本）。没有选项时返回空列表。"""
    st = _snapshot()
    return st.get("choices", []) or []


@mcp.tool()
def get_save_list() -> dict:
    """列出存档：最大槽位数(save_count)、当前已用槽数(save_used)、已占用槽索引列表。

    """
    st = _snapshot()
    return {
        "save_count": st.get("save_count", 0),
        "save_used": st.get("save_used", 0),
        "save_slots": st.get("save_slots", []),
    }


@mcp.tool()
def get_recovered() -> dict:
    """读取 VM 的「容错清单」：本次运行中被容错跳过的脚本错误站点。

    返回 {"total": N, "sites": [{"count": k, "site": "scene=.. line=.. pc=0x.. opcode=.. err=.."}, ...]}。
    total 为累计发生次数，sites 为去重后的站点（含各自次数），最多 200 条。
    未实现/解码不合的命令都会记在这里而不再让游戏停机；
    想恢复「一遇错就停」的旧行为，给引擎进程设置环境变量 SIGLUS_VM_STRICT=1。
    """
    st = _snapshot()
    rec = st.get("recovered")
    if isinstance(rec, dict):
        return rec
    return {"total": 0, "sites": []}


@mcp.tool()
def advance() -> dict:
    """推进对话（注入一次 Enter / 确认键）。返回推进后的状态。推荐使用 skip_to_choice 而不是 advance 多次。

    **结局信号**：当这一句正好命中 `endings_map.toml` 里的判定句时，
    返回里带 `ending = {"name": "<结局名>", "phrase": "<判定句>"}`
    """
    return get_bridge().advance()


@mcp.tool()
def choose(idx: int) -> dict:
    """在选择点选第 idx 项（0 起）。idx 取自 get_choices 的下标。返回选择后的状态。"""
    return get_bridge().choose(idx)


@mcp.tool()
def skip_to_choice() -> dict:
    """快进到下一个选择点。返回到达选择点时的状态及收集到的全部对白。推荐使用 skip_to_choice 而不是 advance 多次。

    返回里带 `skip_lines`（本次快进收集到的全部对白）以及：
    - `skip_stop_reason`：快进为什么停 —— `choice`（到达选择点）/`ending`（命中结局判定句）/
      `halted`（停机）/`time_budget`、`step_budget`（引擎自身预算用尽，默认 40 秒）/
      `requested`（客户端要求停止）；
    - `skip_timeout=true` 表示**不是**正常到达，而是预算用尽后被停止（此时可安全地再次调用 skip，
      已收集的对白仍会在 `skip_lines` 里返回，不会丢失）。

    **结局信号**（文本匹配，见 AGENT.md 17）：快进途中哪一句命中了 `endings_map.toml` 的
    判定句，就在**那一行**上标注 `skip_lines[i].ending = {"name","phrase"}`；
    `skip_endings` 把它们收成 `[{"index": <skip_lines 下标>, "text", "name", "phrase"}]`，
    顶层 `ending` 给出最后一个（即本段的结局）。命中结局时快进会**停在那一句**
    （`skip_stop_reason="ending"`，属正常到达，不是超时）。

    **游戏内日期**：`skip_dates` 给出本次快进跨过的日期及其**确切位置**——
    每项是 `{"index": <skip_lines 下标>, "month","day","weekday","text"}`；
    `skip_lines[i].date` 同时在"首行"和"日期发生变化的行"上标注，
    因此从任一项向后填充即可给每一行标出所属日期（跨多天也会逐条给出）。
    """
    return get_bridge().skip()


@mcp.tool()
def save(slot: int) -> dict:
    """写入指定存档槽 slot。返回存后的状态。

    不要在选项处下一句位置save，否则会出现无法推进的bug。推荐在选项处时先save再choose。
    """
    return get_bridge().save(slot)


@mcp.tool()
def load(slot: int) -> dict:
    """读取存档槽 slot。返回读档后的状态。
    由于引擎缺陷，如果load到选项处，需要advance一次才能choose。
    """
    return get_bridge().load(slot)



if __name__ == "__main__":
    mcp.run()
