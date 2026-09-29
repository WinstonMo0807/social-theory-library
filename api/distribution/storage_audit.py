"""Bounded metadata-only storage accounting. This module never deletes files."""
import os
import stat
from collections import defaultdict
from pathlib import Path


def inspect_storage(roots, *, max_entries=100000):
    seen = set()
    remaining = max_entries
    result = []
    for label, root in roots.items():
        root = Path(root).absolute()
        groups = defaultdict(lambda: {"files": 0, "logical_bytes": 0, "unique_bytes": 0, "allocated_bytes": 0})
        skipped, errors = 0, []
        stack = [root]
        complete = True
        while stack:
            path = stack.pop()
            if remaining <= 0:
                complete = False
                break
            remaining -= 1
            try:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    skipped += 1
                    continue
                if stat.S_ISDIR(info.st_mode):
                    with os.scandir(path) as entries:
                        for entry in entries:
                            stack.append(Path(entry.path))
                            if len(stack) > remaining:
                                complete = False
                                break
                    continue
                if not stat.S_ISREG(info.st_mode):
                    skipped += 1
                    continue
                relative = path.relative_to(root)
                group = relative.parts[0] if len(relative.parts) > 1 else "(root files)"
                row = groups[group]
                row["files"] += 1
                row["logical_bytes"] += info.st_size
                identity = (info.st_dev, info.st_ino)
                if identity not in seen:
                    seen.add(identity)
                    row["unique_bytes"] += info.st_size
                    row["allocated_bytes"] += getattr(info, "st_blocks", (info.st_size + 511) // 512) * 512
            except OSError as exc:
                errors.append({"path": str(path), "error": type(exc).__name__})
        totals = {key: sum(row[key] for row in groups.values()) for key in ("files", "logical_bytes", "unique_bytes", "allocated_bytes")}
        result.append({"label": label, "path": str(root), "complete": complete and not errors,
            **totals, "groups": dict(groups), "skipped_links_or_special": skipped, "errors": errors[:20]})
    return {"read_only": True, "files_deleted": 0, "hardlink_accounting": "unique across roots in listed order",
            "entry_budget": max_entries, "entries_visited": max_entries - remaining, "roots": result,
            "complete": all(row["complete"] for row in result)}
