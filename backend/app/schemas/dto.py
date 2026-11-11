"""请求与响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.entities import APPEND, DB_TYPES, STRATEGIES


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    must_change_password: bool


class MeOut(UserOut):
    workspace_ids: list[int]
    csrf_token: str


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: str = "importer"


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""


class WorkspaceOut(BaseModel):
    id: int
    name: str
    description: str
    member_count: int = 0


class MembersIn(BaseModel):
    user_ids: list[int]


class DatasourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    db_type: str
    host: str
    port: int = Field(gt=0, lt=65536)
    database: str
    username: str
    password: str = ""
    options: dict = {}

    def check_type(self) -> None:
        if self.db_type not in DB_TYPES:
            raise ValueError("db_type")


class DatasourceOut(BaseModel):
    id: int
    name: str
    db_type: str
    host: str
    port: int
    database: str
    username: str
    options: dict


class ColumnOut(BaseModel):
    name: str
    type: str
    comment: str
    nullable: bool
    default: str | None
    is_primary_key: bool


class TableSchemaOut(BaseModel):
    schema_name: str = Field(alias="schema")
    table_name: str
    columns: list[ColumnOut]
    unique_keys: list[dict]
    engine: str

    model_config = {"populate_by_name": True}


class ColumnMapping(BaseModel):
    excel_path: list[str]
    db_column: str


class UnpivotGroup(BaseModel):
    dimension_value: str
    match_prefix: list[str]


class UnpivotMeasure(BaseModel):
    excel_leaf: str
    db_column: str


class Unpivot(BaseModel):
    dimension_column: str
    groups: list[UnpivotGroup]
    measures: list[UnpivotMeasure]
    skip_empty_measures: bool = True


class ConstantMapping(BaseModel):
    db_column: str
    value: str


class Mapping(BaseModel):
    columns: list[ColumnMapping] = []
    unpivot: Unpivot | None = None
    constants: list[ConstantMapping] = []


class RuleOverride(BaseModel):
    db_column: str
    required: bool | None = None
    enum: list[str] | None = None
    pattern: str | None = None
    default: str | None = None
    max_length: int | None = None


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    datasource_id: int
    target_schema: str = ""
    target_table: str
    sheet: str = ""
    header_start_row: int = Field(ge=1, default=1)
    header_row_count: int = Field(ge=1, le=10, default=1)
    strategy: str = APPEND
    business_keys: list[str] = []
    scope_columns: list[str] = []
    mapping: Mapping = Mapping()
    rule_overrides: list[RuleOverride] = []

    def check_strategy(self) -> None:
        if self.strategy not in STRATEGIES:
            raise ValueError("strategy")


class TemplateOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str
    current_version: int
    is_archived: bool
    datasource_id: int | None = None
    target_schema: str = ""
    target_table: str = ""
    sheet: str = ""
    header_start_row: int = 1
    header_row_count: int = 1
    strategy: str = APPEND
    business_keys: list[str] = []
    scope_columns: list[str] = []
    mapping: dict = {}
    rule_overrides: list[dict] = []


class SuggestRequest(BaseModel):
    datasource_id: int
    target_schema: str = ""
    target_table: str
    paths: list[list[str]]
    unpivot_leaf_mode: bool = False


class Suggestion(BaseModel):
    excel_path: list[str]
    db_column: str
    score: int
    reason: str


class SynonymGroupIn(BaseModel):
    terms: list[str] = Field(min_length=1)


class SynonymGroupOut(BaseModel):
    id: int
    terms: list[str]


class ImportMeta(BaseModel):
    template_id: int
    template_version: int
    row_count: int = Field(ge=0)


class ImportOut(BaseModel):
    id: int
    status: str
    template_id: int
    template_version: int
    operator: str = ""
    target_table: str = ""
    strategy: str = ""
    row_count: int = 0
    processed: int = 0
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    counts_exact: bool = True
    error_count: int = 0
    failure_code: str = ""
    failure_message: str = ""
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ImportLogOut(BaseModel):
    id: int
    ts: datetime
    level: str
    code: str
    params: dict
    message: str


class ImportErrorOut(BaseModel):
    id: int
    row_no: int
    column: str
    code: str
    params: dict


class PreviewScopeIn(BaseModel):
    template_id: int
    template_version: int
    scopes: list[dict]


class ResolveIn(BaseModel):
    outcome: str


class Page(BaseModel):
    items: list
    total: int
    page: int
    size: int
