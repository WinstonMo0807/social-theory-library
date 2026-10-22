import type { Metadata } from "next";
import { AuthLayout } from "@/components/auth-layout";

export const metadata: Metadata = { title: "登录" };

export default function LoginPage() {
  return <AuthLayout mode="login" />;
}
