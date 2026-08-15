import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";
import { AuthLayout } from "@/components/auth-layout";

export const metadata: Metadata = { title: "重置密码" };

export default function ResetPasswordPage() {
  return <AuthLayout><Suspense><AuthForm mode="reset" /></Suspense></AuthLayout>;
}
