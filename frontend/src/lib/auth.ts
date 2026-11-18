/**
 * 登录成功后的去向：只接受站内路径，防止开放重定向。
 * redirect 来自 URL 查询参数，必须校验；其它值一律回首页。
 */
export function resolveLoginRedirect(redirect: unknown): string {
  if (typeof redirect !== "string") return "/";
  if (!redirect.startsWith("/") || redirect.startsWith("//")) return "/";
  if (redirect === "/login") return "/";
  return redirect;
}
