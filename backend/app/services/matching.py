"""自动匹配：历史映射 > 注释精确 > 字段名精确 > 同义词 > 包含 > 编辑距离。

一个库字段只分配给得分最高的路径，低于 60 分不自动连线。
"""

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import TableSchema
from app.models.entities import SynonymGroup, SynonymTerm, Template, TemplateVersion
from app.rules.engine import normalize_name

HISTORY = "HISTORY"
COMMENT_EXACT = "COMMENT_EXACT"
NAME_EXACT = "NAME_EXACT"
SYNONYM = "SYNONYM"
CONTAINS = "CONTAINS"
EDIT_DISTANCE = "EDIT_DISTANCE"

MIN_SCORE = 60


def _score(leaf: str, column_name: str, comment: str, synonyms: dict[str, int],
           history: dict[str, str]) -> tuple[int, str]:
    normalized = normalize_name(leaf)
    if history.get(leaf) == column_name:
        return 100, HISTORY
    if comment and normalize_name(comment) == normalized:
        return 90, COMMENT_EXACT
    if normalize_name(column_name) == normalized:
        return 85, NAME_EXACT
    group_of_leaf = synonyms.get(normalized)
    if group_of_leaf is not None and (
        synonyms.get(normalize_name(column_name)) == group_of_leaf
        or (comment and synonyms.get(normalize_name(comment)) == group_of_leaf)
    ):
        return 80, SYNONYM
    if comment and (normalized in normalize_name(comment) or normalize_name(comment) in normalized):
        return 60, CONTAINS
    similarity = SequenceMatcher(None, normalized, normalize_name(column_name)).ratio()
    if similarity >= 0.6:
        return int(similarity * 50), EDIT_DISTANCE
    return 0, ""


def synonym_index(db: Session, workspace_id: int) -> dict[str, int]:
    rows = db.execute(
        select(SynonymTerm.term, SynonymTerm.group_id)
        .join(SynonymGroup, SynonymGroup.id == SynonymTerm.group_id)
        .where(SynonymGroup.workspace_id == workspace_id)
    ).all()
    return {normalize_name(term): group_id for term, group_id in rows}


def history_index(db: Session, workspace_id: int, table: str) -> dict[str, str]:
    """同一目标表的历史映射：路径叶子 -> 库字段。"""
    versions = db.execute(
        select(TemplateVersion.mapping)
        .join(Template, Template.id == TemplateVersion.template_id)
        .where(Template.workspace_id == workspace_id, TemplateVersion.target_table == table)
    ).scalars()
    found: dict[str, str] = {}
    for mapping in versions:
        for column in mapping.get("columns", []):
            path = column.get("excel_path") or []
            if path:
                found[path[-1]] = column["db_column"]
        unpivot = mapping.get("unpivot") or {}
        for measure in unpivot.get("measures", []):
            found[measure["excel_leaf"]] = measure["db_column"]
    return found


def suggest(schema: TableSchema, paths: list[list[str]], leaf_mode: bool, synonyms: dict[str, int],
            history: dict[str, str]) -> list[dict]:
    candidates: list[tuple[int, list[str], str, str]] = []
    for path in paths:
        leaf = path[-1] if path else ""
        key = leaf if leaf_mode else " / ".join(path)
        best = (0, "", "")
        for column in schema.columns:
            score, reason = _score(key, column.name, column.comment, synonyms, history)
            if score > best[0]:
                best = (score, column.name, reason)
        if best[0] >= MIN_SCORE:
            candidates.append((best[0], path, best[1], best[2]))
    # 一个库字段只能被一个路径占用，高分优先。
    candidates.sort(key=lambda item: item[0], reverse=True)
    used: set[str] = set()
    suggestions = []
    for score, path, column, reason in candidates:
        if column in used:
            continue
        used.add(column)
        suggestions.append({"excel_path": path, "db_column": column, "score": score, "reason": reason})
    return suggestions
