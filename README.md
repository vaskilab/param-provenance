# param-provenance

**Schema validation checks the shape of a value. This checks where it came from.**

Catches fabricated tool arguments in LLM agents before they execute. Zero dependencies, Python 3.9+.

[中文文档](README.zh-CN.md) · [Background article](docs/article-zh.md)

---

## The failure this catches

An agent needs to look up a record. The query returns an empty list. The correct
behavior is to tell the user nothing was found.

Instead, the model picks a different numeric-looking field from the context and
passes it as the argument to the next tool — a write.

```
query_ticket(user_id="U10086")  ->  {"tickets": []}
urge_ticket(ticket_id="20261103001")  ->  200 OK
```

That `20261103001` was an **order** ID from an earlier step.

Every technical signal is green. The tool name is correct. The argument is a
non-empty string matching the schema. The API returns 200. No error rate, latency,
or exception dashboard will fire. You find out during business reconciliation,
after the write has landed.

**The value's type was right. Its origin was not.**

## Why schema validation does not help

JSON Schema — including strict / structured-output modes — can express:

- this must be a string
- this must match a pattern
- this must not be empty

It cannot express *"this value must come from the `ticketId` field of a prior
`query_ticket` result."* Origin is outside its expressive range. That check has to
live in your execution layer.

## 30-second quickstart

```bash
git clone https://github.com/vaskilab/param-provenance.git
cd param-provenance
python examples/demo.py
```

No install step, no API key, no network. Five scenarios print their verdicts.

## Usage

Declare where each argument is allowed to come from:

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

Check a call against the trace before executing it:

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

`on_missing` is either `abort` (block the call) or `warn` (record and allow). Use
`warn` while you are still learning your own traffic.

## Prevention, not just detection

Detection tells you the model made something up. Prevention removes its chance to.

Let the model emit a **path**, and have your engine produce the value:

```json
{
  "tool": "urge_ticket",
  "args": { "ticket_id": { "$ref": "steps[1].tickets[0].ticketId" } }
}
```

The engine dereferences it. If the query returned an empty list, resolution fails
cleanly and the call never happens:

```
BLOCK [REF_UNRESOLVED] urge_ticket.ticket_id: path 'tickets[0].ticketId'
not present in result of step 1
```

The model never held a value it could invent. This looks like a small change of
argument format; it actually moves the right to produce values from the model back
to the engine.

## What it checks

| Case | Verdict |
|---|---|
| Value came from the declared tool and path | ALLOW |
| Query returned nothing, model supplied an ID anyway | BLOCK |
| Value exists in the trace but came from a **different tool** | BLOCK |
| Source query **failed**, payload happened to contain an ID | BLOCK |
| Reference points at a nonexistent element | BLOCK |
| Argument has no source rule | ALLOW (unconstrained) |

The third row is the one worth noting. An "is this ID present anywhere in the
context" check passes it. A field-level source rule does not.

## Design notes

- **Only successful results authorize writes.** Partial data from a failed call is
  never a valid source.
- **Causality is respected.** A call cannot draw provenance from a result recorded
  after it.
- **No model in the loop.** Pure rule evaluation over recorded data. Cost is
  effectively zero, so this belongs in the cheapest tier of your eval pipeline,
  not behind an LLM judge.
- **Multiple results accumulate.** Paginated queries all contribute valid sources.

## Scope

This is one check, deliberately narrow. It does **not**:

- detect the other classes of agent hallucination (skipped tool calls, false
  success reports, cross-entity contamination, routing to nonexistent tools)
- decide whether a tool call is semantically appropriate
- replace server-side authorization — validate again on the server, since any
  client-side constraint can be undone by a prompt change or a model upgrade

It is meant to sit alongside those, as the cheapest and most deterministic layer.

## Tests

```bash
python -m unittest discover -s tests -v
```

25 tests, standard library only.

## Status

Early. The API may change. Issues and PRs welcome — particularly real-world
fabrication patterns that the current rules miss.

## License

MIT
