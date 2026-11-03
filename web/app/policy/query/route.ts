import { searchPolicies } from "@/lib/policy-demo/search.server";

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) return Response.json({ detail: "仅接受同站点请求。" }, { status: 403 });
  const text = await request.text();
  if (text.length > 8000) return Response.json({ detail: "问题内容过长。" }, { status: 413 });
  try { return Response.json(await searchPolicies(JSON.parse(text)), { headers: { "Cache-Control": "no-store" } }); }
  catch (error) { return Response.json({ detail: error instanceof Error ? error.message : "无法处理本次检索。" }, { status: 400 }); }
}
