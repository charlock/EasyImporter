/** 用浏览器原生压缩把 JSONL 打成 gzip，提交给后端复核。 */

export async function gzipJsonl(rows: Record<string, unknown>[]): Promise<Blob> {
  const text = rows.map((row) => JSON.stringify(row)).join("\n") + (rows.length ? "\n" : "");
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream("gzip"));
  return new Response(stream).blob();
}
