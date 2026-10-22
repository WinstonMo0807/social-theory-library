import type { Metadata } from "next";
import { AuthLayout } from "@/components/auth-layout";

export const metadata: Metadata = { title: "注册" };

export default function RegisterPage() {
  return <AuthLayout mode="register" />;
}
