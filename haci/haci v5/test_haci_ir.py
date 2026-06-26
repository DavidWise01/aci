#!/usr/bin/env python3
from haci_ir import parse_haci

sample = """# Runtime

! BUILD NETWORK
The runtime initializes workers.
allocate scheduler
? should memory be pooled?
pool memory ?
> latency reduced 18%
! BUILD NETWORK >
BUILD RUNTIME !
runtime verified >
```python
! this is code, not HACI intent
```
"""

doc = parse_haci(sample, "test.haci").to_dict()
nodes = doc["nodes"]

def find(raw):
    for n in nodes:
        if n.get("raw") == raw:
            return n
    raise AssertionError(f"missing node: {raw!r}")

assert find("! BUILD NETWORK")["intent"] == "declare"
assert find("! BUILD NETWORK")["owner"] == "human"
assert find("The runtime initializes workers.")["type"] == "documentation"
assert find("allocate scheduler")["owner"] == "machine"
assert find("? should memory be pooled?")["intent"] == "inquire"
assert find("? should memory be pooled?")["status"] == "pending"
assert find("pool memory ?")["status"] == "pending"
assert find("> latency reduced 18%")["intent"] == "observe"
assert find("! BUILD NETWORK >")["intent"] == "declare"
assert find("! BUILD NETWORK >")["status"] == "verified"
assert find("BUILD RUNTIME !")["status"] == "committed"
assert find("runtime verified >")["status"] == "verified"

code_node = find("! this is code, not HACI intent")
assert code_node["type"] == "code"
assert code_node["owner"] == "runtime"

print("PASS: HACI AST/IR v0.1 parser tests passed")
