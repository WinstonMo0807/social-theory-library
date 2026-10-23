"""Editorial learning-order checks over the original path stage/item IDs."""
from catalog.services.reading_paths import ReadingPathStructureError


def dependency_report(groups):
    items = [row for group in groups for row in group["items"]]
    active = {str(row["id"]): row for row in items if row.get("status", "active") == "active"}
    order = {str(row["id"]): position for position, row in enumerate(items)}
    edges = {identifier: [] for identifier in active}
    problems, relations = [], {"learning_order": 0, "theory_related": 0}
    for identifier, item in active.items():
        for relation in item.get("dependencies", []):
            target, kind = str(relation["item_id"]), relation["kind"]
            relations[kind] += 1
            if target not in active:
                problems.append({"code": "unavailable_dependency", "item_ids": [identifier, target], "detail": "关联材料已移除或撤回，请重新核对先修关系。"})
                continue
            if kind == "learning_order":
                edges[identifier].append(target)
                if order[target] >= order[identifier]:
                    problems.append({"code": "dependency_order", "item_ids": [identifier, target], "detail": "先修材料须排在当前材料之前。"})
    # ponytail: at most 600 materials; a bounded DFS gives the actual conflict path.
    state, stack, positions = {}, [], {}
    def visit(identifier):
        state[identifier] = 1; positions[identifier] = len(stack); stack.append(identifier)
        for target in edges[identifier]:
            if state.get(target) == 1:
                problems.append({"code": "dependency_cycle", "item_ids": stack[positions[target]:] + [target], "detail": "学习顺序形成循环，请调整其中一条先修关系。"})
            elif not state.get(target):
                visit(target)
        stack.pop(); positions.pop(identifier); state[identifier] = 2
    for identifier in edges:
        if not state.get(identifier):
            visit(identifier)
    return {"material_count": len(items), "active_count": len(active), "relation_counts": relations,
            "dependencies_valid": bool(active) and not problems, "problems": problems,
            "notice": "此处检查材料身份与先修顺序。馆藏文件和公开状态仍会在发布及阅读时复核。"}


def validate_dependency_references(groups):
    identifiers = {str(row["id"]) for group in groups for row in group["items"]}
    for group in groups:
        for row in group["items"]:
            seen = set()
            for relation in row.get("dependencies", []):
                target, kind = str(relation["item_id"]), relation["kind"]
                if target not in identifiers or target == str(row["id"]):
                    raise ReadingPathStructureError("依赖须指向本路径中的另一条材料。删除材料前请移除对应依赖。")
                if (target, kind) in seen:
                    raise ReadingPathStructureError("同一材料和同一种关系不能重复。")
                seen.add((target, kind))


def ensure_path_dependencies(groups):
    report = dependency_report(groups)
    if not report["dependencies_valid"]:
        raise ReadingPathStructureError(report["problems"][0]["detail"] if report["problems"] else "路径尚无阅读材料，请先编排内容。")
