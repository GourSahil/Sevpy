import os
import shutil
import subprocess
import time
import re
from pathlib import Path
from libs.path_utils import find_files

class InstallAbort(Exception):
    """Controlled installer abort"""
    pass

class Installer:
    def __init__(self, python_source_directory, version):
        self.name = "Python-Installer"

        self.version = version
        self.prefix_name = f"python-{version}"

        self.source_directory = Path(python_source_directory).resolve()
        self.install_global_dir = Path.home() / ".local" / "opt"
        self.install_version_dir = self.install_global_dir / self.prefix_name

        self.staging_dir = (
            Path.home()
            / ".cache"
            / "python-installer"
            / "stage"
            / self.prefix_name
        )
        self.log_dir = (
            Path.home()
            / ".cache"
            / "sevpy"
            / "logs"
            / self.prefix_name
        )

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.install_version_dir / ".install-manifest"

        try:
            self.install_global_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            raise InstallAbort(
                f"Installation root not writable: {self.install_global_dir}"
            )

    def check_writable_dir(self, dir_path: Path):
        if not dir_path.is_dir():
            raise InstallAbort(f"Not a directory: {dir_path}")

        test_file = dir_path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except PermissionError:
            raise InstallAbort(f"Directory not writable: {dir_path}")

    def validate_source_tree(self):
        if not self.source_directory.is_dir():
            raise InstallAbort("Python source directory does not exist")

        configure = self.source_directory / "configure"
        if not configure.is_file():
            raise InstallAbort("Invalid Python source tree (missing configure)")

    def check_prefix_collision(self):
        if self.install_version_dir.exists():
            if self.manifest_path.exists():
                raise InstallAbort(
                    f"Python {self.version} is already installed at "
                    f"{self.install_version_dir}"
                )
            else:
                raise InstallAbort(
                    f"Installation directory exists but is unmanaged: "
                    f"{self.install_version_dir}"
                )

    def pre_install_step(self):
        self.validate_source_tree()
        self.check_writable_dir(self.install_global_dir)
        self.check_prefix_collision()

    def _run_logged(self, cmd, *, cwd, env=None, log_name):
        log_path = self.log_dir / log_name

        try:
            with open(log_path, "w") as log:
                subprocess.run(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=log,
                    check=True,
                )
        except subprocess.CalledProcessError as e:
            raise InstallAbort(
                f"Command failed: {' '.join(cmd)}\n"
                f"See log: {log_path}"
            )
        except KeyboardInterrupt:
            raise InstallAbort(
                f"Interrupted by user\n"
                f"Partial log: {log_path}"
            )

    def configure(self):
        self.pre_install_step()

        # ---- Install paths ----
        bindir = self.install_version_dir / "bin"
        libdir = self.install_version_dir / "lib"
        incdir = self.install_version_dir / "include"
        mandir = self.install_version_dir / "share" / "man"

        # ---- Configure command ----
        cmd = [
            "./configure",
            f"--prefix={self.install_version_dir}",
            f"--bindir={bindir}",
            f"--libdir={libdir}",
            f"--includedir={incdir}",
            f"--mandir={mandir}",
            "--with-ensurepip=install",
        ]

        print("[*] Configuring build...")
        t1 = time.time()
        self._run_logged(
            cmd,
            cwd=self.source_directory,
            log_name="configure.log",
        )
        t2 = time.time()
        print(f"[+] Configuration complete in {t2 - t1:.1f} seconds.")

    def compile(self):
        # Number of parallel jobs
        jobs = os.cpu_count() or 1

        print(f"[*] Building with {jobs} parallel jobs...")
        t1 = time.time()
        self._run_logged(
            ["make", f"-j{jobs}"],
            cwd=self.source_directory,
            log_name="build.log",
        )
        t2 = time.time()
        print(f"[+] Build complete in {t2 - t1:.1f} seconds.")

    def staged_install(self, enable_tk=True):
        # Ensure build already happened
        # (optional sanity check, not strictly required)
        if not (self.source_directory / "Makefile").exists():
            raise InstallAbort("Makefile missing — did you run configure()?")

        # ---- Prepare staging directory ----
        if self.staging_dir.exists():
            raise InstallAbort(
                f"Staging directory already exists: {self.staging_dir}"
            )

        try:
            self.staging_dir.mkdir(parents=True)
        except PermissionError:
            raise InstallAbort(
                f"Cannot create staging directory: {self.staging_dir}"
            )

        # ---- make altinstall DESTDIR= ----
        print("[*] Installing to staging directory...")
        self._run_logged(
            ["make", "altinstall", f"DESTDIR={self.staging_dir}"],
            cwd=self.source_directory,
            log_name="install.log",
        )

        # Removing the Tkinter Module
        if not enable_tk:
            print("[*] Stripping Tk support from staged install...")

            staged_prefix = self.staging_dir / self.install_version_dir.relative_to("/")

            tk_modules = find_files(
                staged_prefix,
                re.compile(r"^_tkinter.*\.so$"),
                follow_symlinks=False,
            )

            for tk in tk_modules:
                print(f"[*] Removing: {tk}")
                tk.unlink()


    def find_python_binary(self, staged_prefix):
        bin_dir = staged_prefix / "bin"

        if not bin_dir.exists():
            raise InstallAbort(f"Missing bin directory: {bin_dir}")

        candidates = sorted(bin_dir.glob("python3.*"))

        if not candidates:
            raise InstallAbort("No python3.x executable found in staged install")

        for candidate in candidates:
            if not os.access(candidate, os.X_OK):
                continue

            # Verify it runs and reports a version
            try:
                result = subprocess.run(
                    [str(candidate), "-V"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )
            except Exception:
                continue

            version_output = result.stdout.strip() or result.stderr.strip()

            if self.version in version_output:
                return candidate

        raise InstallAbort("No valid Python executable found in staged install")

    def verify_staging(self):
        staged_prefix = self.staging_dir / self.install_version_dir.relative_to("/")

        if not staged_prefix.exists():
            raise InstallAbort(
                f"Staged prefix not found: {staged_prefix}"
            )

        python_bin = self.find_python_binary(staged_prefix)
        print(f"[+] Verified staged Python: {python_bin}")

        # Containment & symlink safety
        for path in staged_prefix.rglob("*"):
            try:
                resolved = path.resolve()
            except FileNotFoundError:
                raise InstallAbort(f"Broken symlink: {path}")

            if not str(resolved).startswith(str(staged_prefix)):
                raise InstallAbort(
                    f"Path escapes install prefix: {path} → {resolved}"
                )

    def write_manifest(self):
        entries = []

        for path in self.install_version_dir.rglob("*"):
            if path.is_file() or path.is_symlink():
                entries.append(str(path))

        try:
            self.manifest_path.write_text("\n".join(entries) + "\n")
        except Exception as e:
            raise InstallAbort(f"Failed to write manifest: {e}")

    def commit_install(self):
        # Path to staged prefix inside DESTDIR
        staged_prefix = self.staging_dir / self.install_version_dir.relative_to("/")

        if not staged_prefix.exists():
            raise InstallAbort("Nothing to commit: staged prefix missing")

        if self.install_version_dir.exists():
            raise InstallAbort(
                f"Install prefix already exists: {self.install_version_dir}"
            )

        try:
            # Ensure parent exists
            self.install_version_dir.parent.mkdir(parents=True, exist_ok=True)

            # Atomic move
            staged_prefix.rename(self.install_version_dir)
        except Exception as e:
            raise InstallAbort(f"Commit failed: {e}")

        # ---- Write manifest ----
        self.write_manifest()

        # ---- Cleanup staging ----
        shutil.rmtree(self.staging_dir, ignore_errors=True)

    def final_thing(self):
        bin_path = self.install_version_dir / "bin"
        print(
            "\nInstallation complete.\n\n"
            "To use this Python version, add the following to your shell:\n\n"
            f'export PATH="{bin_path}:$PATH"\n\n'
            "This does NOT replace the system Python."
        )
