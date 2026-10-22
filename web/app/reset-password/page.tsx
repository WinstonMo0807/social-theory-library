import type { Metadata } from "next";
import { AuthLayout } from "@/components/auth-layout";

export const metadata: Metadata = { title: "重置密码" };

export default function ResetPasswordPage() {
  return <AuthLayout mode="reset" />;
}
