from pathlib import Path
import re
from typing import Iterable, Union, Pattern


def find_files(
    search_dir: Path,
    pattern: Union[str, Pattern[str]],
    *,
    follow_symlinks: bool = False,
) -> list[Path]:
    """
    Recursively search for files under `search_dir` matching a name or regex.

    Parameters
    ----------
    search_dir : Path
        Root directory to search.
    pattern : str | re.Pattern
        Exact filename OR regex pattern applied to file name.
    follow_symlinks : bool
        Whether to follow symlinks during traversal.

    Returns
    -------
    list[Path]
        Matching file paths.
    """
    if not search_dir.is_dir():
        raise ValueError(f"Not a directory: {search_dir}")

    if isinstance(pattern, str):
        regex = re.compile(re.escape(pattern))
    else:
        regex = pattern

    results: list[Path] = []

    for path in search_dir.rglob("*"):
        try:
            if not follow_symlinks and path.is_symlink():
                continue

            if path.is_file() and regex.search(path.name):
                results.append(path)

        except OSError:
            # Permission denied / broken symlink / race condition
            continue

    return results
