# sevpy 🐍
**Secure Python Source Installer & Version Manager**

> Build Python from source. Verify it. Keep your system Python untouched.

---

## 🚀 What is sevpy?

**sevpy** is a Python version installer and manager that builds **official CPython releases directly from source**, installs them into user space, and keeps your **system Python completely untouched**.

It focuses on:
- Security-first installation
- Transparency over convenience
- User-controlled activation
- Zero system-level interference

> There are bugs currently, even in the **stable** code. They'll be fixed soon, if you find any bugs please report them by raising an issue.

---

## 🧩 Design Philosophy

sevpy follows a few strict principles:

- **System Python is never modified**
- **Only official CPython source archives are used**
- **GPG signatures are verified**
- **PATH is never auto-modified**
- **Every version is isolated**

No shims. No silent overrides. No surprises.

---

## 📂 Installation Layout

All Python versions installed by sevpy live under:

```
~/.local/opt/python-<version>/
```

Each version contains its own:
- `bin/`
- `lib/`
- `include/`
- `share/`

This ensures complete isolation and reproducibility.

---

## 🔐 Security Model

### GPG Verification
- Python source archives are verified using Release Manager GPG keys
- Missing keys are explicitly shown to the user
- Verification failure aborts installation

### Python 2.x Warning
- Python 2.x is End-of-Life
- sevpy displays explicit warnings
- GPG verification may be skipped only if signatures do not exist
- No security guarantees are provided

---

## 📌 Commands

### Install Python
```
sevpy install 3.12.2
```

### Install without Tkinter
```
sevpy install 3.12.2 --no-tk
```

### List Installed Versions
```
sevpy list
```

Shows:
- Valid / Broken status
- Installation prefix
- Binary location
- PATH activation status

---

### Activate a Version (Manual)
```
export PATH="$HOME/.local/opt/python-3.12.2/bin:$PATH"
```

Activation is always explicit and user-controlled.

---

### Reinstall Python
```
sevpy reinstall 3.12.2
```

Skip confirmation:
```
sevpy reinstall 3.12.2 --yes
```

---

### Remove a Version
```
sevpy remove 3.8.9
```

---

### Remove Broken Installations
```
sevpy remove-broken
```

---

### Clean Cache and Build Stages
```
sevpy clean
```

---

## 🧪 Broken Install Detection

sevpy detects broken installations by:
- Verifying binary presence
- Running the interpreter
- Matching runtime version with directory version

Broken installs can be safely removed.

---

## 🧰 Tkinter Support

Tkinter is enabled by default.

Disable it if:
- Tk headers are missing
- GUI dependencies cause build failures

```
sevpy install <version> --no-tk
```

Note: Disabling Tkinter may cause some tests or GUI tools to fail.

---

## 🗑️ Cache Locations

sevpy uses only user-space cache directories:

```
~/.cache/sevpy
~/.cache/python-installer
```

---

## 👤 Author

Sahil Gour

Built with clarity, caution, and control in mind.
