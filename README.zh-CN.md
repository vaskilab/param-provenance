# param-provenance

**Schema 校验的是参数的形状，这个库校验的是参数的出身。**

在 LLM Agent 的写操作执行之前，拦住被编造出来的工具参数。零依赖，Python 3.9+。

[English](README.md) · [背景文章](docs/article-zh.md)

---

## 它拦的是哪种故障

Agent 需要查一条记录，查询接口返回空列表。正确行为是告诉用户没查到。

但模型没有停，它从上下文里挑了另一个看起来像 ID 的字段，当作参数传给了下一个工具——一个写操作。

```
query_ticket(user_id="U10086")  ->  {"tickets": []}
urge_ticket(ticket_id="20261103001")  ->  200 OK
```

那个 `20261103001` 是上一步查到的**订单** ID。

所有技术指标都是绿的：工具名对，参数是符合 schema 的非空字符串，接口返回 200。错误率、耗时、异常率没有任何一个看板会报警。你只能在业务对账时发现，而那时写操作已经落库了。

**参数的类型是对的，出身是错的。**

## 为什么 schema 校验解决不了

JSON Schema，包括 strict 模式和结构化输出，能表达：

- 必须是字符串
- 必须匹配某个正则
- 不能为空

它没法表达「**这个值必须来自上一次 `query_ticket` 返回体的 `ticketId` 字段**」。来源约束不在 schema 的表达能力之内，这层校验只能放在执行引擎里。

## 30 秒跑起来

```bash
git clone https://github.com/vaskilab/param-provenance.git
cd param-provenance
python examples/demo.py
```

不用安装、不用 API key、不联网。五个场景直接打印判定结果。

## 用法

先声明每个参数允许的来源：

```json
{
  "tools": {
    "urge_ticket": {
      "ticket_id": {
        "source": { "tool": "query_ticket", "path": "tickets[].ticketId" },
        "on_missing": "abort"
      }
    }
  }
}
```

在执行前对着 trace 校验：

```python
from provenance import RuleSet, Trace, check_call

rules = RuleSet.from_file("rules.json")
trace = Trace()

q = trace.call("query_ticket", {"user_id": "U10086"})
trace.result(q, ok=True, data={"tickets": []})

write = trace.call("urge_ticket", {"ticket_id": "20261103001"})
result = check_call(write, trace, rules)

if result.blocked:
    print(result.report())
    # BLOCK [PARAM_FABRICATION] urge_ticket.ticket_id='20261103001' has no
    # provenance; expected a value from query_ticket.tickets[].ticketId
else:
    execute(write.tool, result.resolved_args)
```

`on_missing` 取 `abort`（拦截）或 `warn`（记录但放行）。还在摸清自己线上流量特征的阶段，建议先用 `warn`。

## 不只是检测，更是预防

检测告诉你模型编了个值。预防让它没有机会编。

让模型只输出**路径**，由引擎产出值：

```json
{
  "tool": "urge_ticket",
  "args": { "ticket_id": { "$ref": "steps[1].tickets[0].ticketId" } }
}
```

引擎负责解引用。如果查询返回的是空列表，解引用会干净地失败，调用根本不会发生：

```
BLOCK [REF_UNRESOLVED] urge_ticket.ticket_id: path 'tickets[0].ticketId'
not present in result of step 1
```

模型手里从来没有过一个它可以编造的值。这看起来只是换了个传参形式，实际上是把「值的产生权」从模型手里收回到了引擎手里。

## 判定范围

| 场景 | 判定 |
|---|---|
| 值来自声明的工具和路径 | ALLOW |
| 查询返回空，模型仍然给出了 ID | BLOCK |
| 值在 trace 里存在，但来自**另一个工具** | BLOCK |
| 来源查询**失败了**，返回体里恰好有个 ID | BLOCK |
| 引用指向不存在的元素 | BLOCK |
| 该参数没有配置来源规则 | ALLOW（不约束） |

第三行最值得注意。「这个 ID 是否在上下文里出现过」这种检查会放行它，字段级来源规则不会。

## 几个设计取舍

- **只有成功的结果才能授权写操作。** 失败调用的部分数据永远不是合法来源。
- **尊重因果顺序。** 一次调用不能从它之后才记录的结果里取得来源。
- **判卷环节没有模型参与。** 纯规则计算，成本接近零，所以它应该待在评测流水线最便宜的那一层，而不是躲在 LLM judge 后面。
- **多次结果累积。** 分页查询的每一页都贡献合法来源。

## 边界

这是一个刻意做窄的检查。它**不做**这些事：

- 不检测其他类别的 Agent 幻觉（该调工具却跳过、失败报成功、跨实体污染、路由到不存在的工具）
- 不判断一次工具调用在语义上是否恰当
- 不替代服务端鉴权——服务端要再校验一遍，因为任何客户端约束都可能被一次 Prompt 改动或模型升级抹掉

它的定位是和那些手段并列，作为最便宜、最确定的那一层。

## 测试

```bash
python -m unittest discover -s tests -v
```

25 个用例，只用标准库。

## 状态

早期项目，API 可能变动。欢迎提 issue 和 PR，尤其欢迎现有规则漏掉的真实编造模式。

## 许可

MIT
