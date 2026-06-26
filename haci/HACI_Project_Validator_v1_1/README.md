# HACI Project Validator v1.1

Run tests:

```bash
python test_haci_project_validator.py
```

Validate a project:

```bash
python haci_project_validator.py examples/clean_project
python haci_project_validator.py examples/bad_project
```

Expected:

- `clean_project` exits 0
- `bad_project` exits 1
