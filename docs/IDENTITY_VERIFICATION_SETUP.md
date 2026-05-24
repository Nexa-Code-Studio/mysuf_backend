# Identity Verification Setup

The identity verification feature uses optional local OCR and face verification dependencies.
They are intentionally separated from the core backend install because some of them require
native system tooling.

## 1. Install core backend dependencies

```bash
venv/bin/pip install -r requirements.txt
```

## 2. Install required system packages

For Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y build-essential python3-dev
```

`insightface` needs a working C/C++ toolchain. The previous install error came from missing `g++`.

## 3. Install optional identity verification dependencies

Using pinned requirements:

```bash
venv/bin/pip install -r requirements-identity.txt
```

Or using project extras:

```bash
venv/bin/pip install -e ".[identity]"
```

If you also want dev tooling:

```bash
venv/bin/pip install -e ".[dev,identity]"
```

## 4. Notes

- If optional identity packages are not installed, the backend still starts.
- In that state, identity verification model loading is skipped and verification attempts will fail gracefully with internal verification errors.
- After installing the optional packages, restart the backend so model preload runs again.
