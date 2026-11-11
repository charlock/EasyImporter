"""模板与同义词组。保存时校验映射与写入策略前提，并生成新版本。"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.pool import get_target
from app.core.db import get_session
from app.core.errors import ApiError
from app.core.security import current_user, ensure_member, require_admin_write
from app.models.entities import (
    ADMIN,
    Datasource,
    SynonymGroup,
    SynonymTerm,
    Template,
    TemplateVersion,
    User,
)
from app.rules.engine import build_rules, normalize_name
from app.schemas.dto import (
    Mapping,
    Suggestion,
    SuggestRequest,
    SynonymGroupIn,
    SynonymGroupOut,
    TemplateIn,
    TemplateOut,
)
from app.services.matching import history_index, suggest, synonym_index
from app.services.templates import validate_template

router = APIRouter(tags=["templates"])


def _out(template: Template, version: TemplateVersion | None) -> TemplateOut:
    base = TemplateOut(id=template.id, workspace_id=template.workspace_id, name=template.name,
                       description=template.description, current_version=template.current_version,
                       is_archived=template.is_archived)
    if version is None:
        return base
    return base.model_copy(update={
        "datasource_id": version.datasource_id, "target_schema": version.target_schema,
        "target_table": version.target_table, "sheet": version.sheet,
        "header_start_row": version.header_start_row, "header_row_count": version.header_row_count,
        "strategy": version.strategy, "business_keys": version.business_keys,
        "scope_columns": version.scope_columns, "mapping": version.mapping,
        "rule_overrides": version.rule_overrides,
    })


def _template(db: Session, workspace_id: int, template_id: int) -> Template:
    template = db.get(Template, template_id)
    if template is None or template.workspace_id != workspace_id:
        raise ApiError("NOT_FOUND")
    return template


def _version(db: Session, template: Template) -> TemplateVersion | None:
    return db.get(TemplateVersion, (template.id, template.current_version))


@router.get("/workspaces/{workspace_id}/templates", response_model=list[TemplateOut])
def list_templates(workspace_id: int, user: User = Depends(current_user), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    templates = db.scalars(select(Template).where(Template.workspace_id == workspace_id,
                                                   Template.is_archived.is_(False)).order_by(Template.id)).all()
    return [_out(item, _version(db, item)) for item in templates]


@router.post("/workspaces/{workspace_id}/templates", response_model=TemplateOut)
def create_template(workspace_id: int, payload: TemplateIn, user: User = Depends(require_admin_write),
                    db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    schema, db_type = _resolve(db, payload)
    validate_template(payload, schema, db_type)
    template = Template(workspace_id=workspace_id, name=payload.name, description=payload.description)
    db.add(template)
    db.flush()
    version = _new_version(template, 1, payload, schema.schema, user)
    db.add(version)
    db.commit()
    return _out(template, version)


@router.get("/workspaces/{workspace_id}/templates/{template_id}", response_model=TemplateOut)
def get_template(workspace_id: int, template_id: int, user: User = Depends(current_user),
                 db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    return _out(template, _version(db, template))


@router.put("/workspaces/{workspace_id}/templates/{template_id}", response_model=TemplateOut)
def update_template(workspace_id: int, template_id: int, payload: TemplateIn,
                    user: User = Depends(require_admin_write), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    schema, db_type = _resolve(db, payload)
    validate_template(payload, schema, db_type)
    template.name = payload.name
    template.description = payload.description
    template.current_version += 1
    version = _new_version(template, template.current_version, payload, schema.schema, user)
    db.add(version)
    db.commit()
    return _out(template, version)


@router.delete("/workspaces/{workspace_id}/templates/{template_id}")
def delete_template(workspace_id: int, template_id: int, user: User = Depends(require_admin_write),
                    db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    template.is_archived = True
    db.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/templates/{template_id}/clone", response_model=TemplateOut)
def clone_template(workspace_id: int, template_id: int, user: User = Depends(require_admin_write),
                   db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    source = _template(db, workspace_id, template_id)
    current = _version(db, source)
    clone = Template(workspace_id=workspace_id, name=f"{source.name} 副本", description=source.description)
    db.add(clone)
    db.flush()
    if current is not None:
        db.add(TemplateVersion(
            template_id=clone.id, version=1, datasource_id=current.datasource_id,
            target_schema=current.target_schema, target_table=current.target_table, sheet=current.sheet,
            header_start_row=current.header_start_row, header_row_count=current.header_row_count,
            strategy=current.strategy, business_keys=current.business_keys,
            scope_columns=current.scope_columns, mapping=current.mapping,
            rule_overrides=current.rule_overrides, created_by=user.id,
        ))
    db.commit()
    return _out(clone, _version(db, clone))


@router.get("/workspaces/{workspace_id}/templates/{template_id}/rules")
def template_rules(workspace_id: int, template_id: int, user: User = Depends(current_user),
                   db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    version = _version(db, template)
    if version is None:
        return []
    datasource = db.get(Datasource, version.datasource_id)
    schema = get_target(datasource).get_table_schema(version.target_schema or None, version.target_table)
    mapping = Mapping.model_validate(version.mapping)
    from app.services.templates import mapped_columns

    covered = mapped_columns(mapping)
    return [rule.to_dict() for rule in build_rules(schema.columns, version.rule_overrides)
            if rule.db_column in covered]


@router.post("/workspaces/{workspace_id}/templates/suggest-mapping", response_model=list[Suggestion])
def suggest_mapping(workspace_id: int, payload: SuggestRequest, user: User = Depends(require_admin_write),
                    db: Session = Depends(get_session)):
    if user.role != ADMIN:
        raise ApiError("FORBIDDEN")
    ensure_member(db, user, workspace_id)
    datasource = db.get(Datasource, payload.datasource_id)
    if datasource is None:
        raise ApiError("NOT_FOUND")
    schema = get_target(datasource).get_table_schema(payload.target_schema or None, payload.target_table)
    return suggest(schema, payload.paths, payload.unpivot_leaf_mode,
                   synonym_index(db, workspace_id), history_index(db, workspace_id, payload.target_table))


@router.get("/workspaces/{workspace_id}/synonym-groups", response_model=list[SynonymGroupOut])
def list_synonyms(workspace_id: int, user: User = Depends(current_user), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    return _groups(db, workspace_id)


@router.post("/workspaces/{workspace_id}/synonym-groups", response_model=SynonymGroupOut)
def create_synonym(workspace_id: int, payload: SynonymGroupIn, user: User = Depends(require_admin_write),
                   db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    group = SynonymGroup(workspace_id=workspace_id)
    db.add(group)
    db.flush()
    _replace_terms(db, workspace_id, group.id, payload.terms)
    db.commit()
    return SynonymGroupOut(id=group.id, terms=_terms(db, group.id))


@router.put("/workspaces/{workspace_id}/synonym-groups/{group_id}", response_model=SynonymGroupOut)
def update_synonym(workspace_id: int, group_id: int, payload: SynonymGroupIn,
                   user: User = Depends(require_admin_write), db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    group = _group(db, workspace_id, group_id)
    db.query(SynonymTerm).filter(SynonymTerm.group_id == group.id).delete()
    _replace_terms(db, workspace_id, group.id, payload.terms)
    db.commit()
    return SynonymGroupOut(id=group.id, terms=_terms(db, group.id))


@router.delete("/workspaces/{workspace_id}/synonym-groups/{group_id}")
def delete_synonym(workspace_id: int, group_id: int, user: User = Depends(require_admin_write),
                   db: Session = Depends(get_session)):
    ensure_member(db, user, workspace_id)
    group = _group(db, workspace_id, group_id)
    db.query(SynonymTerm).filter(SynonymTerm.group_id == group.id).delete()
    db.delete(group)
    db.commit()
    return {"ok": True}


def _resolve(db: Session, payload: TemplateIn):
    if payload.strategy not in {"APPEND", "UPSERT", "REPLACE_SCOPE"}:
        raise ApiError("VALIDATION_FAILED", {"field": "strategy"})
    datasource = db.get(Datasource, payload.datasource_id)
    if datasource is None:
        raise ApiError("NOT_FOUND")
    try:
        schema = get_target(datasource).get_table_schema(payload.target_schema or None, payload.target_table)
    except Exception as exc:
        raise ApiError("DATASOURCE_UNREACHABLE", {"reason": type(exc).__name__}) from exc
    return schema, datasource.db_type


def _new_version(template: Template, version: int, payload: TemplateIn, schema_name: str,
                 user: User) -> TemplateVersion:
    return TemplateVersion(
        template_id=template.id, version=version, datasource_id=payload.datasource_id,
        target_schema=schema_name or payload.target_schema, target_table=payload.target_table,
        sheet=payload.sheet, header_start_row=payload.header_start_row,
        header_row_count=payload.header_row_count, strategy=payload.strategy,
        business_keys=payload.business_keys, scope_columns=payload.scope_columns,
        mapping=payload.mapping.model_dump(), rule_overrides=[item.model_dump() for item in payload.rule_overrides],
        created_by=user.id,
    )


def _groups(db: Session, workspace_id: int) -> list[SynonymGroupOut]:
    groups = db.scalars(select(SynonymGroup).where(SynonymGroup.workspace_id == workspace_id)).all()
    return [SynonymGroupOut(id=group.id, terms=_terms(db, group.id)) for group in groups]


def _terms(db: Session, group_id: int) -> list[str]:
    return list(db.scalars(select(SynonymTerm.term).where(SynonymTerm.group_id == group_id)))


def _group(db: Session, workspace_id: int, group_id: int) -> SynonymGroup:
    group = db.get(SynonymGroup, group_id)
    if group is None or group.workspace_id != workspace_id:
        raise ApiError("NOT_FOUND")
    return group


def _replace_terms(db: Session, workspace_id: int, group_id: int, terms: list[str]) -> None:
    seen: set[str] = set()
    for term in terms:
        normalized = normalize_name(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        db.add(SynonymTerm(group_id=group_id, workspace_id=workspace_id, term=term.strip()))
    try:
        db.flush()
    except IntegrityError as exc:
        raise ApiError("SYNONYM_TERM_CONFLICT") from exc
