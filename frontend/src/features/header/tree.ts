/** 复合表头识别，见设计方案第 8 节。
 *
 * 输入是已经从 Excel 取出的单元格矩阵和合并区域，不依赖 ExcelJS，
 * 这样解析（在 Worker 里）和识别可以分开测试。
 */

export interface MergeRange {
  /** 0 基，含端点。 */
  top: number;
  left: number;
  bottom: number;
  right: number;
}

export interface HeaderCell {
  value: string;
}

/** 一个叶子列：清理后的路径和它在表里的列号（0 基）。 */
export interface HeaderLeaf {
  column: number;
  path: string[];
  /** 同名路径加的序号，首个为 0。 */
  duplicateIndex: number;
}

export interface HeaderNode {
  label: string;
  children: HeaderNode[];
  /** 叶子节点对应的列号；中间节点为空。 */
  column: number | null;
}

export interface HeaderTree {
  roots: HeaderNode[];
  leaves: HeaderLeaf[];
  /** 出现了重复路径的列，界面上需要提示。 */
  duplicated: HeaderLeaf[];
}

const FULLWIDTH_OFFSET = 0xfee0;

/** 全角转半角，去掉首尾空白和换行。 */
export function cleanCell(raw: string): string {
  const half = raw.replace(/[！-～]/g, (char) =>
    String.fromCharCode(char.charCodeAt(0) - FULLWIDTH_OFFSET),
  );
  return half.replace(/[\r\n]+/g, " ").trim();
}

function master(row: number, column: number, merges: MergeRange[]): { row: number; column: number } {
  for (const merge of merges) {
    if (row >= merge.top && row <= merge.bottom && column >= merge.left && column <= merge.right) {
      return { row: merge.top, column: merge.left };
    }
  }
  return { row, column };
}

/**
 * 从表头区域构造表头树。
 * @param cells 行优先的矩阵，只包含表头行（第 0 行对应 headerStartRow）。
 * @param merges 与表头相交的合并区域，坐标相对整个 sheet（0 基）。
 * @param headerStartRow 表头起始行，0 基，用于把合并区域换算到矩阵坐标。
 */
export function buildHeaderTree(
  cells: HeaderCell[][],
  merges: MergeRange[],
  headerStartRow: number,
): HeaderTree {
  const rowCount = cells.length;
  const columnCount = cells.reduce((max, row) => Math.max(max, row.length), 0);

  const relativeMerges = merges.map((merge) => ({
    ...merge,
    top: merge.top - headerStartRow,
    bottom: merge.bottom - headerStartRow,
  }));

  const rawPaths: { column: number; path: string[] }[] = [];
  for (let column = 0; column < columnCount; column += 1) {
    const path: string[] = [];
    for (let row = 0; row < rowCount; row += 1) {
      const origin = master(row, column, relativeMerges);
      const value = cleanCell(cells[origin.row]?.[origin.column]?.value ?? "");
      if (!value) continue;
      // 纵向合并会造成相邻两层值相同，只保留一层。
      if (path[path.length - 1] === value) continue;
      path.push(value);
    }
    if (path.length) rawPaths.push({ column, path });
  }

  const seen = new Map<string, number>();
  const leaves: HeaderLeaf[] = rawPaths.map(({ column, path }) => {
    const duplicateIndex = seen.get(path.join("\u0000")) ?? 0;
    seen.set(path.join("\u0000"), duplicateIndex + 1);
    const labelled =
      duplicateIndex === 0 ? path : [...path.slice(0, -1), `${path[path.length - 1]}#${duplicateIndex + 1}`];
    return { column, path: labelled, duplicateIndex };
  });

  return { roots: toTree(leaves), leaves, duplicated: leaves.filter((leaf) => leaf.duplicateIndex > 0) };
}

function toTree(leaves: HeaderLeaf[]): HeaderNode[] {
  const roots: HeaderNode[] = [];
  for (const leaf of leaves) {
    let level = roots;
    leaf.path.forEach((label, depth) => {
      const last = depth === leaf.path.length - 1;
      let node = level.find((item) => item.label === label);
      if (!node) {
        node = { label, children: [], column: last ? leaf.column : null };
        level.push(node);
      }
      if (last) node.column = leaf.column;
      level = node.children;
    });
  }
  return roots;
}

/** 路径的展示文本。 */
export function pathLabel(path: string[]): string {
  return path.join(" / ");
}
