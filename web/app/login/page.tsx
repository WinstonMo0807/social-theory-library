import type { Metadata } from "next";
import { AuthLayout } from "@/components/auth-layout";
import { AuthSessionResume } from "@/components/auth-session-resume";

export const metadata: Metadata = { title: "登录" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = await searchParams;
  const next = typeof params.next === "string" ? params.next : undefined;
  const form = <AuthLayout mode="login" />;
  return params.resume === "1" ? <AuthSessionResume next={next}>{form}</AuthSessionResume> : form;
}
