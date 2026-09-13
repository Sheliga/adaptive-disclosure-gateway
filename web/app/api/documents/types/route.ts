import { proxyGet } from "@/lib/proxy";

export async function GET(): Promise<Response> {
  return proxyGet("/documents/types");
}
