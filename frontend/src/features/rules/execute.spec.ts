/** 与后端 tests/test_core.py::test_rules_match_shared_fixtures 读同一批样例，保证前后端结论一致。 */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import type { ColumnInfo, RuleOverride } from "@/lib/types";

import { buildRules, findDuplicateKeys, validateRow } from "./execute";

interface Fixture {
  columns: ColumnInfo[];
  overrides?: RuleOverride[];
  cases: {
    row_no: number;
    row: Record<string, unknown>;
    expected_errors: string[];
    expected_values?: Record<string, unknown>;
  }[];
}

const FIXTURE_DIR = join(__dirname, "../../../../fixtures/rules");
const files = readdirSync(FIXTURE_DIR).filter((name) => name.endsWith(".json"));

describe("shared rule fixtures", () => {
  it("has at least one fixture", () => expect(files.length).toBeGreaterThan(0));

  for (const name of files) {
    const fixture = JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf-8")) as Fixture;
    const rules = buildRules(fixture.columns, fixture.overrides ?? []);
    for (const testCase of fixture.cases) {
      it(`${name} row ${testCase.row_no}`, () => {
        const { cleaned, errors } = validateRow(rules, testCase.row, testCase.row_no);
        expect(errors.map((error) => error.code)).toEqual(testCase.expected_errors);
        for (const [key, value] of Object.entries(testCase.expected_values ?? {})) {
          expect(cleaned[key]).toEqual(value);
        }
      });
    }
  }
});

describe("findDuplicateKeys", () => {
  it("marks every duplicated row", () => {
    const rows = [
      { _row: 1, serial_no: "S1" },
      { _row: 2, serial_no: "S2" },
      { _row: 3, serial_no: "S1" },
    ];
    expect(findDuplicateKeys(rows, ["serial_no"]).map((error) => error.row_no)).toEqual([1, 3]);
  });
});
