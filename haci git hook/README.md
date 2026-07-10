# haci-git · the human skin

Write plain Markdown. Commit it. Git becomes the MACI envelope for free.

| you write (`.haci`) | git supplies |
|---|---|
| `!` command / `?` question / `>` evidence | id = commit hash |
| authorial case convention | from = author |
| — | ts = commit time |
| — | refs = parent commits (the DAG, already acyclic) |
| — | authority = signature (see below) |

## the two ternary axes

- **speech act**  `{ ! command, ? question, > evidence }`
- **authority**   `{ + sovereign, 0 delegated, − advisory }` — resolved from the *signature*, not the text, so file content can never forge authority.

Sign with your governor key → `sovereign`. Sign with an authorized agent key → `delegated`. Leave unsigned → `advisory`.

## use

```
git config core.hooksPath .githooks   # once — arms the fence-swallow guard
python3 haci_git.py lint orders.haci   # refuse if an open fence swallows a command
python3 haci_git.py envelope .         # git log -> validated MACI stream + seal
python3 haci_git.py selftest           # fence-immunity / swallow-guard / ternary
```

The pre-commit hook refuses to record any `.haci` with an unterminated fence — the one
live vector an independent audit surfaced (a truncated fence silently demotes a `!` command
to inert CODE). It renders as ordinary Markdown in the GitHub file view.
