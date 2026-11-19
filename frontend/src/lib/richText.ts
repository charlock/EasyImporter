import DOMPurify from "dompurify";

/** 说明字段富文本的白名单：只保留 Tiptap 常用排版标签与链接，去掉脚本、
 * 事件属性与其它标签；展示与回填编辑器前都先过一遍，防止存入的 HTML
 * 在别处被原样渲染时带入恶意内容。 */
const ALLOWED_TAGS = [
  "p", "h1", "h2", "h3", "strong", "em", "s",
  "ul", "ol", "li", "a", "blockquote", "code", "pre", "hr", "br",
];
const ALLOWED_ATTR = ["href", "target", "rel"];

/** 净化一段说明 HTML；空串与纯文本原样返回。 */
export function sanitizeHtml(html: string): string {
  if (!html.trim()) return "";
  return DOMPurify.sanitize(html, { ALLOWED_TAGS, ALLOWED_ATTR });
}
