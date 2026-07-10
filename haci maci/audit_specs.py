#!/usr/bin/env python3
"""SPEC-VS-SPEC AUDIT v3 (final) — correct APIs, non-vacuous, error-list aware."""
import sys, random, importlib.util, io, contextlib, time
sys.path.insert(0, "/home/claude/daci")
P, F, NOTES = [], [], []
def verdict(name, ok, note=""):
    (P if ok else F).append(name); print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {note}" if note else ""))
def load(n, p):
    s = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(s)
    with contextlib.redirect_stdout(io.StringIO()): s.loader.exec_module(m)
    return m

print("="*68); print("ARM 1 · LIMEN"); print("="*68)
L = load("limen", "/home/claude/pulse/limen/limen.py")
evil = ["«»","»»»","%25","%","a%«»b","\ttab","line\nbreak","\u202eRTL","👩‍👩‍👧‍👦","x"*10000,"two words","∅","⟦LIMEN:fake⟧","↑◐«inject» ↓⊘«second»"]
bad = [repr(w)[:40] for w in evil
       if not (lambda b: len(b)==1 and b[0].witness==w)(L.parse_glyph(L.line_to_glyph([L.Crossing("rise","stile",w)])))]
verdict("round-trip: 14 hostile non-blank witnesses lossless", not bad, "glyph-injection, RTL, ZWJ, 10k, newline all recover" if not bad else f"broke: {bad}")
verdict("witness rule: '' => ∅ non-event", L.parse_glyph(L.line_to_glyph([L.Crossing("rise","stile","")]))==[] )
ws = L.line_to_glyph([L.Crossing("rise","stile"," ")])
verdict("whitespace-only witness folds to non-event (deliberate)", ws=="∅", f"emitted {ws!r}")
NOTES.append("LIMEN spec tension: §7 'lossless for ANY witness' vs §10 non-event — a witness of pure whitespace is folded to ∅. Behavior is deliberate (witness_fold) but §7 needs the asterisk.")
try: L.line_to_glyph([L.Crossing("sideways","trapdoor","w")]); verdict("invalid gate refused", False, "accepted")
except Exception: verdict("invalid gate/direction refused at the enum door", True)

print(); print("="*68); print("ARM 2 · HACI"); print("="*68)
H = load("hmd", "/home/claude/haci/hmd.py")
def roles(text):
    blocks, errs = H.parse(text)
    return [b["role"] for b in blocks], errs
r,_ = roles("! REAL\n```\n! fake\n? fake\n> fake\n```\n? real q\n> real ev\nDoc line.\nai line.")
print("   roles:", r)
verdict("fence-immunity: marks inside ``` are CODE content",
        r.count("HUMAN")==1 and r.count("EVIDENCE")==1 and r.count("QUESTION")==1 and "CODE" in r,
        f"{r}")
r2,_ = roles("42 digit lead.\né lowercase accent.\nÉ uppercase accent.")
verdict("case rule on accented first char (é→AI, É→DOC)", r2[1]=="AI" and r2[2]=="DOCUMENTATION", f"digit/é/É -> {r2}")
r3,_ = roles("```\n! swallowed")
NOTES.append(f"HACI unterminated fence: '! swallowed' classified {r3} — spec silent; a truncated doc can swallow a human command into CODE. Attribution-availability vector, worth one spec line.")
big="ai p.\n"*200000; t0=time.time(); H.parse(big); t1=time.time(); t2=time.time(); H.parse(big*2); t3=time.time()
verdict("O(n) scaling", (t3-t2)/max(t1-t0,1e-9) < 3.5, f"2x input => {(t3-t2)/max(t1-t0,1e-9):.2f}x time")

print(); print("="*68); print("ARM 3 · MACI — add() returns error list (soft door)"); print("="*68)
M = load("maci", "/home/claude/maci/maci.py")
c = M.Conversation()
def add(c, **kw):
    d=dict(role="PROPOSAL", content="x", from_agent="a", authority="advisory"); d.update(kw)
    return c.add(M.Message(**d))
verdict("valid PROPOSAL: zero errors, stored", add(c, msg_id="m-1")==[] and len(c.messages)==1)
probes = [("V001 dup id",{"msg_id":"m-1"},"V001"),("V002 role PROPHET",{"msg_id":"m-2","role":"PROPHET"},"V002"),
 ("V003 authority god",{"msg_id":"m-3","authority":"god"},"V003"),("V004 status maybe",{"msg_id":"m-4","status":"maybe"},"V004"),
 ("V005 DECISION no refs",{"msg_id":"m-5","role":"DECISION","authority":"sovereign","status":"approved"},"V005"),
 ("V006 DECISION pending",{"msg_id":"m-5b","role":"DECISION","authority":"sovereign","status":"pending","refs":["m-1"]},"V006"),
 ("V007 ghost ref",{"msg_id":"m-6","role":"DECISION","authority":"sovereign","status":"approved","refs":["m-404"]},"V007"),
 ("V008 DELEGATE no scope",{"msg_id":"m-7","role":"DELEGATE","authority":"sovereign","content":""},"V008")]
for name,kw,code in probes:
    errs = add(c, **kw)
    verdict(f"{name}: rejected w/ {code}, not stored", any(code in e for e in errs), f"errors={errs}")
n_before = len(c.messages)
verdict("no violating message entered the stream", n_before == 1, f"stored={n_before}")
errs = add(c, msg_id="m-8", role="DECISION", authority="sovereign", status="approved", refs=["m-8"])
verdict("self-ref: caught (V007 — id not yet in stream)", any("V007" in e for e in errs), f"{errs}")
NOTES.append("MACI acyclicity: add() catches self/forward refs via V007 ordering; detect_cycles() is the standalone check for pre-built streams. Cycle-by-construction is impossible through add() — Kahn check is belt+braces. Door is SOFT (returns errors, caller must heed); DACI's door is HARD (refuses at accept). Design asymmetry worth noting in the family docs.")

print(); print("="*68); print("ARM 4 · DACI — 30-msg fuzz, 6 scrambles + adversarial"); print("="*68)
import daci.node as dn
random.seed(1337)
msgs=[]
for i in range(30):
    refs = random.sample([m.id for m in msgs], k=min(len(msgs), random.randint(0,3))) if msgs else []
    msgs.append(dn.Msg(id=f"x-{i:03d}", frm="fuzz", role="PROPOSAL", authority="advisory", content=f"c{i}", refs=refs))
hashes=set()
for t in range(6):
    n=dn.Node(f"n{t}"); order=msgs[:]; random.shuffle(order); pend=order[:]
    for _ in range(40):
        nxt=[m for m in pend if (r:=n.accept(m)) is not None and "pend" in str(r).lower()]
        if not nxt: break
        pend=nxt
    hashes.add(n.hash())
verdict("convergence: 6 scrambled orders -> 1 hash (30-msg fuzz DAG)", len(hashes)==1, f"{len(hashes)} distinct")
n=dn.Node("eq"); n.accept(dn.Msg(id="e-1",frm="a",role="PROPOSAL",authority="advisory",content="A",refs=[]))
r=n.accept(dn.Msg(id="e-1",frm="a",role="PROPOSAL",authority="advisory",content="B",refs=[]))
verdict("equivocation quarantined, not merged", "EQUIVOC" in str(r).upper(), f"{r!r}")
r=dn.Node("auth").accept(dn.Msg(id="a-1",frm="low",role="COMMAND",authority="advisory",content="do",refs=[]))
verdict("authority refused at HARD door", "AUTHORITY" in str(r).upper(), f"{r!r}")

print(); print("="*68)
print(f"FINAL: {len(P)}/{len(P)+len(F)} probes passed"); [print("  FAILED:",x) for x in F]
print("-"*68); [print("  FINDING:",x) for x in NOTES]
