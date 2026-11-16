/** 模板页状态机（方案 §4.2）：S0 未选择 / S1 查看 / S2 新建 / S3 编辑。
 *
 * 纯函数，与 Vue 无关，可单测。页面层负责：脏时确认（select / startNew 前）、
 * 路由同步（select → /templates/:id，startNew → /templates/new）、
 * 表单快照（dirty / valid 的计算见页面）。
 */

export type TemplatePageState = "S0" | "S1" | "S2" | "S3";

export interface TemplatePageModel {
  state: TemplatePageState;
  /** 进入 S2/S3 之前的状态；取消时回到这里；S0/S1 时为 null。 */
  returnState: "S0" | "S1" | null;
  /** S1/S3 时当前模板的 id；S2 时为 null。 */
  selectedId: number | null;
  /** 进入 S2 前选中的模板 id；S2 取消时回到 S1 用它恢复选择。 */
  previousId: number | null;
}

export const initialModel: TemplatePageModel = {
  state: "S0",
  returnState: null,
  selectedId: null,
  previousId: null,
};

export type TemplateStateEvent =
  | { type: "select"; id: number }
  | { type: "clear" }
  | { type: "startNew" }
  | { type: "startEdit" }
  | { type: "cancel" }
  | { type: "saveSuccess"; id: number };

/** 状态转移。调用方在 select / startNew 前先做脏确认；本函数不弹确认。 */
export function transition(model: TemplatePageModel, event: TemplateStateEvent): TemplatePageModel {
  switch (event.type) {
    case "select":
      return { state: "S1", returnState: null, selectedId: event.id, previousId: null };
    case "clear":
      return { state: "S0", returnState: null, selectedId: null, previousId: null };
    case "startNew": {
      if (model.state === "S2") return model;
      return {
        state: "S2",
        returnState: model.state === "S1" || model.state === "S3" ? "S1" : "S0",
        selectedId: null,
        previousId: model.selectedId,
      };
    }
    case "startEdit":
      if (model.state !== "S1") return model;
      return { ...model, state: "S3", returnState: "S1" };
    case "cancel": {
      if (model.state !== "S2" && model.state !== "S3") return model;
      const back = model.returnState ?? "S0";
      return {
        state: back,
        returnState: null,
        selectedId: back === "S1" ? (model.state === "S2" ? model.previousId : model.selectedId) : null,
        previousId: null,
      };
    }
    case "saveSuccess":
      if (model.state !== "S2" && model.state !== "S3") return model;
      return { state: "S1", returnState: null, selectedId: event.id, previousId: null };
    default:
      return model;
  }
}

/** 按钮启用状态（方案 §4.3）。模板里所有按钮只绑这张表，不写临时判断。 */
export interface TemplateButtonStates {
  templateSelect: boolean;
  addNew: boolean;
  quickImport: boolean;
  uploadSample: boolean;
  edit: boolean;
  configure: boolean;
  cancel: boolean;
  save: boolean;
}

export function computeButtonStates(
  model: TemplatePageModel,
  opts: { valid: boolean; dirty: boolean; saving: boolean },
): TemplateButtonStates {
  const { state } = model;
  const inEdit = state === "S2" || state === "S3";
  return {
    templateSelect: true,
    addNew: state !== "S2",
    quickImport: state !== "S0",
    uploadSample: state !== "S0",
    edit: state === "S1",
    configure: inEdit,
    cancel: inEdit,
    save: inEdit && opts.valid && opts.dirty && !opts.saving,
  };
}

/** 保存必填项缺失清单（与页面 valid 同源：valid = 清单为空）。 */
export type MissingRequiredKey = "name" | "datasource" | "targetTable" | "mapping";

export function missingRequiredFields(form: {
  name: string;
  datasource_id: number | null;
  target_table: string;
  mapping: { columns: { db_column: string }[] };
}): MissingRequiredKey[] {
  const missing: MissingRequiredKey[] = [];
  if (form.name.trim() === "") missing.push("name");
  if (form.datasource_id == null) missing.push("datasource");
  if (form.target_table === "") missing.push("targetTable");
  if (!form.mapping.columns.some((column) => column.db_column.trim() !== "")) {
    missing.push("mapping");
  }
  return missing;
}

/** Viewer 是否可编辑：仅新建/编辑态（库的 editable 默认 false = 只读）。 */
export function viewerEditable(model: TemplatePageModel): boolean {
  return model.state === "S2" || model.state === "S3";
}
