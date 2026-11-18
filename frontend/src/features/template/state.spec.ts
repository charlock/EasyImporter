import { describe, expect, it } from "vitest";

import {
  computeButtonStates,
  initialModel,
  missingRequiredFields,
  transition,
  viewerEditable,
  type TemplatePageModel,
} from "./state";

const S1: TemplatePageModel = { state: "S1", returnState: null, selectedId: 7, previousId: null };
const S2fromS1: TemplatePageModel = { state: "S2", returnState: "S1", selectedId: null, previousId: 7 };
const S2fromS0: TemplatePageModel = { state: "S2", returnState: "S0", selectedId: null, previousId: null };
const S3: TemplatePageModel = { state: "S3", returnState: "S1", selectedId: 7, previousId: null };

describe("transition", () => {
  it("S0 选现有模板 → S1", () => {
    expect(transition(initialModel, { type: "select", id: 7 })).toEqual(S1);
  });
  it("S1 选另一模板 → S1（换 id）", () => {
    expect(transition(S1, { type: "select", id: 9 })).toEqual({
      state: "S1",
      returnState: null,
      selectedId: 9,
      previousId: null,
    });
  });
  it("清除选择 → S0", () => {
    expect(transition(S1, { type: "clear" })).toEqual(initialModel);
  });
  it("S0 新建 → S2（回 S0）", () => {
    expect(transition(initialModel, { type: "startNew" })).toEqual(S2fromS0);
  });
  it("S1 新建 → S2（记住原模板，回 S1）", () => {
    expect(transition(S1, { type: "startNew" })).toEqual(S2fromS1);
  });
  it("S2 再新建 → 保持 S2", () => {
    expect(transition(S2fromS1, { type: "startNew" })).toEqual(S2fromS1);
  });
  it("S1 点编辑 → S3", () => {
    expect(transition(S1, { type: "startEdit" })).toEqual(S3);
  });
  it("S0/S2 点编辑 → 不变", () => {
    expect(transition(initialModel, { type: "startEdit" })).toEqual(initialModel);
    expect(transition(S2fromS1, { type: "startEdit" })).toEqual(S2fromS1);
  });
  it("S2 取消 → 回到进入前的 S1 并恢复选择", () => {
    expect(transition(S2fromS1, { type: "cancel" })).toEqual(S1);
  });
  it("S2（从 S0 来）取消 → 回到 S0", () => {
    expect(transition(S2fromS0, { type: "cancel" })).toEqual(initialModel);
  });
  it("S3 取消 → 回到 S1", () => {
    expect(transition(S3, { type: "cancel" })).toEqual(S1);
  });
  it("S1/S0 取消 → 不变", () => {
    expect(transition(S1, { type: "cancel" })).toEqual(S1);
    expect(transition(initialModel, { type: "cancel" })).toEqual(initialModel);
  });
  it("S2 保存成功 → S1（新 id）", () => {
    expect(transition(S2fromS1, { type: "saveSuccess", id: 12 })).toEqual({
      state: "S1",
      returnState: null,
      selectedId: 12,
      previousId: null,
    });
  });
  it("S3 保存成功 → S1（原 id）", () => {
    expect(transition(S3, { type: "saveSuccess", id: 7 })).toEqual(S1);
  });
  it("S1 保存成功 → 不变", () => {
    expect(transition(S1, { type: "saveSuccess", id: 7 })).toEqual(S1);
  });
});

describe("computeButtonStates", () => {
  it("S0：只有模板下拉与 + 可用", () => {
    expect(computeButtonStates(initialModel, { valid: true, dirty: true, saving: false })).toEqual({
      templateSelect: true,
      addNew: true,
      quickImport: false,
      uploadSample: false,
      edit: false,
      configure: false,
      cancel: false,
      save: false,
    });
  });
  it("S1：编辑可用，配置/取消/保存禁用", () => {
    const states = computeButtonStates(S1, { valid: true, dirty: true, saving: false });
    expect(states.edit).toBe(true);
    expect(states.configure).toBe(false);
    expect(states.cancel).toBe(false);
    expect(states.save).toBe(false);
    expect(states.quickImport).toBe(true);
    expect(states.uploadSample).toBe(true);
  });
  it("S2：+ 禁用，保存需 valid && dirty && !saving", () => {
    const base = { valid: true, dirty: true, saving: false };
    expect(computeButtonStates(S2fromS1, base).addNew).toBe(false);
    expect(computeButtonStates(S2fromS1, base).save).toBe(true);
    expect(computeButtonStates(S2fromS1, { ...base, valid: false }).save).toBe(false);
    expect(computeButtonStates(S2fromS1, { ...base, dirty: false }).save).toBe(false);
    expect(computeButtonStates(S2fromS1, { ...base, saving: true }).save).toBe(false);
  });
  it("S3：配置/取消可用，保存同条件", () => {
    const states = computeButtonStates(S3, { valid: true, dirty: true, saving: false });
    expect(states.configure).toBe(true);
    expect(states.cancel).toBe(true);
    expect(states.save).toBe(true);
    expect(states.edit).toBe(false);
  });
});

describe("viewerEditable", () => {
  it("仅 S2/S3 可编辑", () => {
    expect(viewerEditable(initialModel)).toBe(false);
    expect(viewerEditable(S1)).toBe(false);
    expect(viewerEditable(S2fromS1)).toBe(true);
    expect(viewerEditable(S3)).toBe(true);
  });
});

describe("missingRequiredFields", () => {
  const base = {
    name: "销售月度",
    datasource_id: 1,
    target_table: "sales_monthly",
    mapping: { columns: [{ db_column: "serial_no" }] },
  };
  it("完整表单 → 空清单", () => {
    expect(missingRequiredFields(base)).toEqual([]);
  });
  it("逐项缺失都能报出", () => {
    expect(missingRequiredFields({ ...base, name: "  " })).toEqual(["name"]);
    expect(missingRequiredFields({ ...base, datasource_id: null })).toEqual(["datasource"]);
    expect(missingRequiredFields({ ...base, target_table: "" })).toEqual(["targetTable"]);
    expect(missingRequiredFields({ ...base, mapping: { columns: [{ db_column: " " }] } })).toEqual([
      "mapping",
    ]);
  });
  it("UPSERT 没选业务键 → 报 businessKeys；选了就不报", () => {
    expect(missingRequiredFields({ ...base, strategy: "UPSERT", business_keys: [] })).toEqual([
      "businessKeys",
    ]);
    expect(
      missingRequiredFields({ ...base, strategy: "UPSERT", business_keys: ["uscc"] }),
    ).toEqual([]);
  });
  it("APPEND / REPLACE_SCOPE 不用业务键", () => {
    expect(missingRequiredFields({ ...base, strategy: "APPEND", business_keys: [] })).toEqual([]);
    expect(missingRequiredFields({ ...base, strategy: "REPLACE_SCOPE", business_keys: [] })).toEqual(
      [],
    );
  });
  it("多项缺失按固定顺序返回", () => {
    expect(
      missingRequiredFields({ name: "", datasource_id: null, target_table: "", mapping: { columns: [] } }),
    ).toEqual(["name", "datasource", "targetTable", "mapping"]);
  });
  it("UPSERT 缺业务键时排在清单末尾", () => {
    expect(
      missingRequiredFields({
        name: "",
        datasource_id: null,
        target_table: "",
        mapping: { columns: [] },
        strategy: "UPSERT",
        business_keys: [],
      }),
    ).toEqual(["name", "datasource", "targetTable", "mapping", "businessKeys"]);
  });
});
