import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";
import { AuthLayout } from "@/components/auth-layout";

export const metadata: Metadata = { title: "登录" };

export default function LoginPage() {
  return <AuthLayout><Suspense><AuthForm mode="login" /></Suspense></AuthLayout>;
}
