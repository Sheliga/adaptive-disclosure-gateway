import { proxyMultipartPost } from "@/lib/proxy";

export async function POST(request: Request): Promise<Response> {
  return proxyMultipartPost("/documents/execute", request);
}
