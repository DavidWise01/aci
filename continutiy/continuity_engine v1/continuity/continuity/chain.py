"""
THE CHAIN — continuity across time.

The suite proves the conversation survives the crossing between skins. The chain
proves it survives the crossing between VERSIONS: each substrate is sealed into a
canonical manifest, signed (who), timestamped against an external RFC-3161
authority (when), and linked to its predecessor by prev_root. Reuses the
closure-loop discipline: the anchor points outside the repo, and the verifier
recomputes everything.

Signing/timestamping degrade honestly: on failure the field is marked 'absent'
with a reason, never faked.
"""
import os, json, base64, subprocess, urllib.request
from typing import List, Optional
from .substrate import Msg
from .projections import to_M
from .canonical import canon, sha


def manifest(S: List[Msg], prev_root: Optional[str]) -> bytes:
    body = {
        "schema": "continuity-anchor/1",
        "substrate": to_M(S),                 # canonical machine form = the sealed bytes
        "substrate_digest": "sha256:" + sha(to_M(S).encode("utf-8")),
        "lineage": {"prev_root": prev_root, "relation": "temporal/structural, not causal"},
    }
    return canon(body)


def _key(keystore):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    os.makedirs(keystore, exist_ok=True)
    p = os.path.join(keystore, "continuity_ed25519.pem")
    if os.path.exists(p):
        priv = serialization.load_pem_private_key(open(p, "rb").read(), password=None)
    else:
        priv = Ed25519PrivateKey.generate()
        open(p, "wb").write(priv.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        os.chmod(p, 0o600)
    return priv


def anchor(S: List[Msg], out_dir: str, keystore: str,
           prev_root: Optional[str] = None,
           tsa_url="https://freetsa.org/tsr",
           tsa_ca="https://freetsa.org/files/cacert.pem",
           tsa_cert="https://freetsa.org/files/tsa.crt") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    mbytes = manifest(S, prev_root)
    mpath = os.path.join(out_dir, "manifest.json")
    open(mpath, "wb").write(mbytes)
    root = "sha256:" + sha(mbytes)

    rec = {"root": root, "prev_root": prev_root,
           "signature": {"status": "absent"}, "timestamp": {"status": "absent"}}

    # WHO — Ed25519 over the manifest bytes
    try:
        from cryptography.hazmat.primitives import serialization
        priv = _key(keystore)
        sig = priv.sign(mbytes)
        open(os.path.join(out_dir, "manifest.sig.b64"), "w").write(base64.b64encode(sig).decode() + "\n")
        open(os.path.join(out_dir, "signer_public.pem"), "wb").write(
            priv.public_key().public_bytes(serialization.Encoding.PEM,
                                            serialization.PublicFormat.SubjectPublicKeyInfo))
        rec["signature"] = {"status": "present", "algorithm": "ed25519",
                            "proves": "this key signed these exact bytes",
                            "not": "an identity unless the key is published"}
    except Exception as e:
        rec["signature"] = {"status": "absent", "reason": str(e)}

    # WHEN — RFC-3161 over the manifest
    try:
        tsq = os.path.join(out_dir, "manifest.tsq"); tsr = os.path.join(out_dir, "manifest.tsr")
        ca = os.path.join(out_dir, "tsa_ca.pem"); cert = os.path.join(out_dir, "tsa_cert.pem")
        subprocess.run(["openssl", "ts", "-query", "-data", mpath, "-sha256", "-cert", "-out", tsq],
                       check=True, capture_output=True)
        req = urllib.request.Request(tsa_url, data=open(tsq, "rb").read(),
                                     headers={"Content-Type": "application/timestamp-query"})
        open(tsr, "wb").write(urllib.request.urlopen(req, timeout=30).read())
        for url, dest in [(tsa_ca, ca), (tsa_cert, cert)]:
            open(dest, "wb").write(urllib.request.urlopen(url, timeout=30).read())
        v = subprocess.run(["openssl", "ts", "-verify", "-data", mpath, "-in", tsr,
                            "-CAfile", ca, "-untrusted", cert], capture_output=True, text=True)
        if "Verification: OK" in (v.stdout + v.stderr):
            rep = subprocess.run(["openssl", "ts", "-reply", "-in", tsr, "-text"],
                                 capture_output=True, text=True).stdout
            t = next((l.split("Time stamp:", 1)[1].strip() for l in rep.splitlines()
                      if "Time stamp:" in l), "")
            rec["timestamp"] = {"status": "present", "standard": "RFC-3161",
                                "asserted_time": t, "tsa": tsa_url,
                                "proves": "manifest existed by this time, per the TSA"}
        else:
            rec["timestamp"] = {"status": "absent", "reason": "token did not verify"}
    except Exception as e:
        rec["timestamp"] = {"status": "absent", "reason": str(e)}

    open(os.path.join(out_dir, "anchor.json"), "w").write(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return rec
