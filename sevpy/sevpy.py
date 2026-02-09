#!/usr/bin/env python3

import os
import shutil
import sys
import tarfile
import subprocess
import re
import requests as req
from tqdm import tqdm
from pathlib import Path
from colorama import Fore, init as colorama_init

colorama_init(autoreset=True)

from libs.installer import Installer, InstallAbort

SEVPY_VERSION = "v1.0.0"

# Installation Root
INSTALL_ROOT = Path.home() / ".local" / "opt"
SEVPY_CACHE = Path.home() / ".cache" / "sevpy"
INSTALLER_STAGE = Path.home() / ".cache" / "python-installer" / "stage"

# ----------------------------
# GPG helpers (unchanged logic)
# ----------------------------

def extract_key_id(gpg_output):
    match = re.search(r"using RSA key ([A-F0-9]{40})", gpg_output)
    if not match:
        raise RuntimeError("Could not extract GPG key ID")
    return match.group(1)


def download_file(url, out_path):
    r = req.get(url, stream=True, timeout=(10, 60))
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} while downloading {url}")

    total = r.headers.get("Content-Length")
    total = int(total) if total else None

    with open(out_path, "wb") as f, tqdm(
        total=total,
        desc=f"Downloading {os.path.basename(out_path)}",
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as pbar:
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            f.write(chunk)
            pbar.update(len(chunk))


def gpg_import_key(key_id):
    print(f"[!] Importing GPG key {key_id} from keys.openpgp.org")
    subprocess.run(
        [
            "gpg",
            "--keyserver",
            "hkps://keys.openpgp.org",
            "--recv-keys",
            key_id,
        ],
        check=True,
    )


def gpg_verify(archive_path, asc_path):
    result = subprocess.run(
        ["gpg", "--verify", asc_path, archive_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode == 0:
        print("[+] GPG signature verified")
        return True

    if "No public key" in result.stderr:
        key_id = extract_key_id(result.stderr)

        print("\n[!] Missing GPG public key")
        print(f"[!] Key ID: {key_id}")
        print("[!] This key belongs to a Python Release Manager")

        choice = input("Import this key? [y/N]: ").strip().lower()
        if choice != "y":
            print("[X] User declined key import")
            return False

        gpg_import_key(key_id)

        retry = subprocess.run(
            ["gpg", "--verify", asc_path, archive_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if retry.returncode == 0:
            print("[+] GPG signature verified after key import")
            return True

        print("[X] Verification failed after importing key")
        print(retry.stderr)
        return False

    print("[X] GPG verification failed")
    print(result.stderr)
    return False

# ----------------------------
# Source extraction
# ----------------------------

def extract_source(archive_path, out_dir):
    print(f"[+] Extracting {archive_path}")
    with tarfile.open(archive_path, mode="r:xz") as tar:
        tar.extractall(path=out_dir)
    print("[+] Extraction complete")

def confirm_eol_version(version, skip=False):
    if skip: # Only passed when reinstalling
        return True, False
    if not version.startswith("2."):
        choice = input(f"[*] Do you want to install python-{version}? [y/N]: ").strip().lower()
        if choice == "y" or choice == "":
            return True, False
        else:
            return False, False

    print(Fore.RED + "[!] WARNING: Python 2.x is end-of-life and no longer maintained.")
    print(Fore.YELLOW + "[!] Compilation may fail and security issues are unpatched.")
    print(Fore.YELLOW + "[!] sevpy provides NO guarantees for Python 2.x builds.\n")

    choice = input("Do you want to continue? [y/N]: ").strip().lower()
    return choice == "y", True

def install(version, reinstall=False, enable_tkinter=True):
    eol = confirm_eol_version(version, skip=reinstall)
    if not eol[0]:
        print(Fore.RED + "[*] Aborted by user.")
        return
    base_url = f"https://www.python.org/ftp/python/{version}"
    archive = f"Python-{version}.tar.xz"
    signature = f"{archive}.asc"

    cache_dir = Path.home() / ".cache" / "sevpy"
    src_dir = cache_dir / "src"

    cache_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    archive_path = cache_dir / archive
    sig_path = cache_dir / signature

    try:
        print(f"[+] Downloading Python {version}")
        download_file(f"{base_url}/{archive}", archive_path)
        download_file(f"{base_url}/{signature}", sig_path)

        if not eol[1] and not gpg_verify(archive_path, sig_path):
            print(Fore.RED + "[X] Aborting: source is not trusted")
            return
        
        if eol[1]:
            print(Fore.YELLOW + "[*] Skipping GPG Signature check, No  GPG signatures found!")

        extract_source(archive_path, src_dir)
        source_tree = src_dir / f"Python-{version}"

        if not source_tree.exists():
            raise RuntimeError("Extracted source directory not found")

        installer = Installer(
            python_source_directory=source_tree,
            version=version,
        )

        installer.configure()
        installer.compile()
        installer.staged_install(enable_tk=enable_tkinter)
        installer.verify_staging()
        installer.commit_install()
        installer.final_thing()

    except InstallAbort as e:
        print(Fore.RED + f"[X] Installation aborted: {e}")

    except Exception as e:
        print(Fore.RED + f"[X] Error: {e}")

    finally:
        try:
            archive_path.unlink()
            sig_path.unlink()
        except Exception:
            pass

def check_activated(version: str) -> bool:
    """
    Check whether python<major>.<minor> resolved from PATH
    matches the requested version (including patch).
    """
    parts = version.split(".")
    if len(parts) < 2:
        return False

    major, minor = parts[0], parts[1]
    want_patch = parts[2] if len(parts) > 2 else None

    python_exe = shutil.which(f"python{major}.{minor}")
    if python_exe is None:
        return False

    try:
        code = (
            "import sys;"
            "v=sys.version_info;"
            "print(f'{v.major}.{v.minor}.{v.micro}')"
        )

        result = subprocess.run(
            [python_exe, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
            check=True,
        )

        found = result.stdout.strip()

        if want_patch is None:
            return found.startswith(f"{major}.{minor}.")
        else:
            return found == version

    except Exception:
        return False

def find_installed_versions():
    versions = {}

    if not INSTALL_ROOT.exists():
        return versions

    for entry in INSTALL_ROOT.iterdir():
        if not entry.is_dir():
            continue

        if not entry.name.startswith("python-"):
            continue

        version = entry.name.removeprefix("python-")
        bin_dir = entry / "bin"

        info = {
            "prefix": entry,
            "python": None,
            "runtime_version": None,
            "valid": False,
            "activated": False,
            "error": None,
        }

        if not bin_dir.exists():
            info["error"] = "missing bin directory"
            versions[version] = info
            continue

        candidates = sorted(bin_dir.glob("python3.*"))

        if not candidates:
            info["error"] = "no python3.x executable found"
            versions[version] = info
            continue

        for candidate in candidates:
            if not os.access(candidate, os.X_OK):
                continue

            try:
                result = subprocess.run(
                    [
                        str(candidate),
                        "-c",
                        (
                            "import sys;"
                            "v=sys.version_info;"
                            "print(f'{v.major}.{v.minor}.{v.micro}')"
                        )
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5,
                    check=True,
                )
            except Exception as e:
                info["error"] = str(e)
                continue

            runtime_version = result.stdout.strip()

            if runtime_version == version:
                info["python"] = candidate
                info["runtime_version"] = runtime_version
                info["valid"] = True
                info["error"] = None
                break

        # activation is a PATH question, not a filesystem one
        info["activated"] = check_activated(version)

        versions[version] = info

    return versions

def clean():
    removed_any = False

    for path in [SEVPY_CACHE, INSTALLER_STAGE]:
        if not path.exists():
            continue

        print(f"[!] Cleaning {path}")
        try:
            shutil.rmtree(path)
            removed_any = True
            print(f"[+] Removed {path}")
        except Exception as e:
            print(f"[X] Failed to remove {path}: {e}")

    if not removed_any:
        print("[+] Nothing to clean")

def remove_broken():
    installed = find_installed_versions()
    removed_any = False

    for version, info in installed.items():
        if info["valid"]:
            continue

        prefix = info["prefix"]
        print(f"[!] Removing broken Python {version}")
        try:
            shutil.rmtree(prefix)
            removed_any = True
            print(f"[+] Removed {prefix}")
        except Exception as e:
            print(f"[X] Failed to remove {prefix}: {e}")

    if not removed_any:
        print("[+] No broken installations found")

def remove_version(version, no_confirm=False):
    prefix = INSTALL_ROOT / f"python-{version}"

    if not prefix.exists():
        print(f"[X] Python {version} is not installed")
        return

    if not no_confirm:
        print(Fore.YELLOW + f"[!] You are about to permanently remove Python {version}")
        print(Fore.YELLOW + "[!] This action is irreversible.")

        confirm = input("Are you sure you want to continue? [y/N]: ").strip().lower()
        if confirm != "y":
            print(Fore.RED + "[*] Aborted.")
            return

    print(Fore.CYAN + f"[!] Removing Python {version} ...")
    try:
        shutil.rmtree(prefix)
        print(f"[+] Removed Python {version}")
    except Exception as e:
        print(f"[X] Failed to remove Python {version}: {e}")

def reinstall_version(version, no_check=False, enable_tkinter=True):
    prefix = INSTALL_ROOT / f"python-{version}"

    if not no_check and not prefix.exists():
        print(f"[X] Python {version} is not installed — cannot reinstall")
        return

    if prefix.exists():
        print(Fore.YELLOW + f"[!] Reinstalling Python {version}")
        print(Fore.YELLOW + "[!] Existing installation will be removed")

        confirm = input("Are you sure you want to continue? [y/N]: ").strip().lower()
        if confirm != "y":
            print(Fore.RED + "[*] Aborted.")
            return

        try:
            shutil.rmtree(prefix)
            print(f"[+] Removed existing Python {version}")
        except Exception as e:
            print(f"[X] Failed to remove existing installation: {e}")
            return
    else:
        print(Fore.YELLOW + f"[!] Python {version} not found — proceeding with fresh install")

    # Proceed with fresh install
    install(version, reinstall=True, enable_tkinter=enable_tkinter)

def is_pyinstaller_internal_flag(arg):
    return arg.startswith("-") and arg not in ("--yes", "--no-tk")

def print_help():
    print(f"""
{Fore.CYAN}sevpy {SEVPY_VERSION}{Fore.RESET}
{Fore.CYAN}Python source installer & version manager{Fore.RESET}
{Fore.YELLOW}*{Fore.CYAN}- Made by Sahil Gour -{Fore.YELLOW}*{Fore.RESET}

USAGE:
  sevpy <command> [options]
COMMANDS:
    version
    :  See the currently installed Version.
  install <version>
    :  Download, build, and install Python from source.
  reinstall <version> [--yes]
    :  Reinstall an existing Python version.
    :  --yes    Skip confirmation prompt.
  list
    :  List all installed Python versions and their status.
  remove <version> [--yes]
    :  Remove a specific Python version.
    :  --yes    Skip confirmation prompt.
  remove-broken
    :  Remove all detected broken installations.
  clean
    :  Remove cached sources and staging directories.
  version
    :  Show sevpy version information.
  help
    :  To seek help regarding sevpy usage.
FLAGS:
    --no-tk
    :    Disable Tkinter support (passed to installer).
    :    May cause some tests to fail, but can resolve certain build issues.
EXAMPLES:
  sevpy install 3.12.2
  sevpy list
  sevpy remove 3.8.9
  sevpy reinstall 3.12.2 --yes
  sevpy reinstall 3.7.13 --no-tk
  sevpy install 2.7.18 --no-tk
  sevpy clean

{Fore.CYAN}NOTES:{Fore.RESET}
  • {Fore.CYAN}Installed Pythons live in: {Fore.GREEN}{INSTALL_ROOT}{Fore.RESET}
  • {Fore.YELLOW}System Python is never modified.{Fore.RESET}
  • {Fore.YELLOW}PATH must be configured manually by the user.{Fore.RESET}
""")

def is_multiprocessing_reentry(arg: str) -> bool:
    return (
        "multiprocessing" in arg
        or "resource_tracker" in arg
        or arg.startswith("from multiprocessing")
    )

def main():
    if len(sys.argv) < 2:
        print_help()
        return

    import multiprocessing
    multiprocessing.freeze_support()

    if len(sys.argv) < 2:
        print_help()
        return

    args = [
        a for a in sys.argv[1:]
        if not is_pyinstaller_internal_flag(a)
        and not is_multiprocessing_reentry(a)
    ]
    if not args:
        return

    cmd = args[0].lower()

    if cmd == "help":
        print_help()
    elif cmd == "version":
        print(Fore.CYAN + f"SevPY {SEVPY_VERSION}")
    elif cmd == "install":
        if len(args) < 2:
            print(Fore.RED + "Error: specify a version (e.g. 3.12.2)")
            return
        version = args[1]
        enable_tkinter = not ("--no-tk" in args) # checking if --no-tk is provided as argument to prevent tkinter installation
        for _version, info in find_installed_versions().items():
            if version == _version:
                print(Fore.GREEN + f"[+] Version Python-{version} already exists at {info['prefix']}")
                return
        install(version, enable_tkinter=enable_tkinter)

    elif cmd == "list":
        installed = find_installed_versions()
        if len(installed.keys()) == 0:
            print(Fore.YELLOW + "[+] No versions installed!")
        else:
            for version, info in installed.items():
                status = Fore.GREEN + "OK" if info["valid"] else Fore.RED + "BROKEN"
                print(f"Python {version} [{status}]")

                if info["valid"]:
                    print(f"  Prefix : {info['prefix']}")
                    print(f"  Binary: {info['python']}")
                    bin_path = info['prefix'] / "bin"
                    if info["activated"]:
                        print(f"  Status: {Fore.GREEN} Activated (on PATH)")
                    else:
                        print(f"  Status: {Fore.YELLOW} Not Activated (not on PATH)")
                        print(Fore.YELLOW + f'  To Add it to Path : export PATH="{bin_path}:$PATH"')
                else:
                    print(f"  Prefix : {info['prefix']}")
                    print(f"  Reason: {info['error']}")
    elif cmd == "remove-broken":
        remove_broken()
    elif cmd == "remove":
        if len(args) < 2:
            print(Fore.RED + "Error: specify a version (e.g. 3.12.2)")
            return
        version = args[1]
        no_confirm = "--yes" in args
        remove_version(version, no_confirm=no_confirm)

    elif cmd == "reinstall":
        if len(args) < 2:
            print(Fore.RED + "Error: specify a version (e.g. 3.12.2)")
            return
        version = args[1]
        no_confirm = "--yes" in args
        enable_tkinter = not ("--no-tk" in args)
        reinstall_version(version, no_check=no_confirm, enable_tkinter=enable_tkinter)
    elif cmd == "clean":
        clean()
    else:
        print(Fore.RED + f"Unknown command: {cmd}")
        print_help()

if __name__ == "__main__":
    main()
