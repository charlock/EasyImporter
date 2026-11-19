"""模板与同义词组。保存时校验映射与写入策略前提，并生成新版本。"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
    TemplateSample,
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


def _out(template: Template, version: TemplateVersion | None,
         sample_file_name: str | None = None) -> TemplateOut:
    base = TemplateOut(id=template.id, workspace_id=template.workspace_id, name=template.name,
                       description=template.description, current_version=template.current_version,
                       is_archived=template.is_archived,
                       has_sample=sample_file_name is not None, sample_file_name=sample_file_name)
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


def _sample_names(db: Session, template_ids: list[int]) -> dict[int, str]:
    """一次查询取回多模板的样例文件名，避免列表页逐行 N+1。"""
    if not template_ids:
        return {}
    rows = db.execute(
        select(TemplateSample.template_id, TemplateSample.file_name)
        .where(TemplateSample.template_id.in_(template_ids))
    ).all()
    return {row[0]: row[1] for row in rows}


@router.get("/workspaces/{workspace_id}/templates", response_model=list[TemplateOut])
def list_templates(workspace_id: int, include_archived: bool = False,
                   user: User = Depends(current_user), db: Session = Depends(get_session)):
    """默认只列未归档模板；模板列表页传 include_archived=true 以便删除后仍能看到
    已归档行（带“已归档”徽章）。模板下拉等其他调用方不传参，行为不变。"""
    ensure_member(db, user, workspace_id)
    query = select(Template).where(Template.workspace_id == workspace_id)
    if not include_archived:
        query = query.where(Template.is_archived.is_(False))
    templates = db.scalars(query.order_by(Template.id)).all()
    samples = _sample_names(db, [item.id for item in templates])
    return [_out(item, _version(db, item), samples.get(item.id)) for item in templates]


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
def get_template(workspace_id: int, template_id: int, version: int | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_session)):
    """默认返回当前版本；传 version 则返回该历史版本（模板每次保存都产生新版本，
    历史版本保留在 template_versions 表里）。导入详情页用它取任务提交时的映射。"""
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    sample = db.get(TemplateSample, template.id)
    if version is None:
        return _out(template, _version(db, template), sample.file_name if sample else None)
    wanted = db.get(TemplateVersion, (template.id, version))
    if wanted is None:
        raise ApiError("NOT_FOUND")
    return _out(template, wanted, sample.file_name if sample else None)


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


@router.post("/workspaces/{workspace_id}/templates/{template_id}/sample")
async def upload_template_sample(workspace_id: int, template_id: int,
                                 file: UploadFile = File(...),
                                 user: User = Depends(require_admin_write),
                                 db: Session = Depends(get_session)):
    """上传/替换模板样例原文件（.xlsx）。每模板只保留最新一份，再次编辑时
    由编辑器下载回显。文件只做格式与大小校验，不解析内容（解析仍在前端）。"""
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    name = file.filename or ""
    if not name.lower().endswith(".xlsx"):
        raise ApiError("INVALID_FILE_TYPE")
    data = await file.read()
    max_bytes = get_settings().upload_max_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise ApiError("PAYLOAD_TOO_LARGE")
    if not data.startswith(b"PK\x03\x04"):
        raise ApiError("INVALID_FILE_TYPE")
    existing = db.get(TemplateSample, template.id)
    if existing is None:
        db.add(TemplateSample(template_id=template.id, file_name=name, data=data))
    else:
        existing.file_name = name
        existing.data = data
    db.commit()
    return {"ok": True, "file_name": name, "size": len(data)}


@router.get("/workspaces/{workspace_id}/templates/{template_id}/sample")
def download_template_sample(workspace_id: int, template_id: int,
                             user: User = Depends(current_user),
                             db: Session = Depends(get_session)):
    """下载模板样例原文件；未上传过样例时 404。"""
    ensure_member(db, user, workspace_id)
    template = _template(db, workspace_id, template_id)
    sample = db.get(TemplateSample, template.id)
    if sample is None:
        raise ApiError("NOT_FOUND")
    filename = sample.file_name or "sample.xlsx"
    return Response(
        content=sample.data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


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
    source_sample = db.get(TemplateSample, source.id)
    if source_sample is not None:
        db.add(TemplateSample(template_id=clone.id, file_name=source_sample.file_name,
                              data=source_sample.data))
    db.commit()
    return _out(clone, _version(db, clone),
                source_sample.file_name if source_sample else None)


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
