"""统一错误码。message 是默认中文说明，前端按 code + params 翻译。"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

ERRORS: dict[str, tuple[int, str]] = {
    "UNAUTHORIZED": (401, "未登录或会话已过期"),
    "FORBIDDEN": (403, "没有权限执行该操作"),
    "CSRF_INVALID": (403, "请求缺少或包含无效的 CSRF 令牌"),
    "VALIDATION_FAILED": (422, "请求参数不合法"),
    "NOT_FOUND": (404, "资源不存在"),
    "DATASOURCE_UNREACHABLE": (502, "连接目标库失败"),
    "DATASOURCE_HOST_NOT_ALLOWED": (422, "主机不在允许的白名单内"),
    "DATASOURCE_IN_USE": (409, "数据源仍被模板引用，不能删除"),
    "WORKSPACE_NOT_EMPTY": (409, "工作区下仍有模板或导入任务，不能删除"),
    "TEMPLATE_HEADER_MISMATCH": (422, "上传文件缺少模板要求的表头"),
    "TEMPLATE_VERSION_CHANGED": (409, "模板已被修改，请重新加载后再提交"),
    "TEMPLATE_INVALID": (422, "模板配置不合法"),
    "UNIQUE_KEY_REQUIRED": (422, "UPSERT 策略要求目标表存在与业务键对应的唯一索引"),
    "UPSERT_AMBIGUOUS_UNIQUE_KEY": (422, "MySQL 目标表的其他唯一索引包含已映射的列，无法使用 UPSERT"),
    "TABLE_ENGINE_NOT_TRANSACTIONAL": (422, "MySQL 目标表不是 InnoDB，无法保证事务回滚"),
    "PAYLOAD_TOO_LARGE": (413, "上传文件或解压后的数据超过上限"),
    "INVALID_FILE_TYPE": (422, "只接受 .xlsx 文件"),
    "IMPORT_FILES_EXPIRED": (410, "原始文件已超过保留期被清理，不能重新执行"),
    "IMPORT_NOT_RETRYABLE": (409, "当前任务状态不允许重新执行"),
    "IMPORT_NOT_RESOLVABLE": (409, "只有状态未知的任务需要人工核对"),
    "ROW_COUNT_MISMATCH": (422, "提交的行数与声明不一致"),
    "LOGIN_LOCKED": (429, "登录失败次数过多，账号已临时锁定"),
    "LOGIN_FAILED": (401, "用户名或密码错误"),
    "PASSWORD_CHANGE_REQUIRED": (403, "首次登录必须先修改密码"),
    "USER_DISABLED": (403, "账号已停用"),
    "USERNAME_TAKEN": (409, "用户名已存在"),
    "MEMBER_NOT_FOUND": (422, "成员列表包含不存在的用户"),
    "SYNONYM_TERM_CONFLICT": (409, "同义词已存在于其他分组"),
}


class ApiError(HTTPException):
    def __init__(self, code: str, params: dict | None = None, message: str | None = None):
        status, default_message = ERRORS.get(code, (400, "请求失败"))
        self.code = code
        self.params = params or {}
        super().__init__(status_code=status, detail=message or default_message)


def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.detail, "params": exc.params},
    )
