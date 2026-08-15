import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthForm } from "@/components/auth-form";
import { AuthLayout } from "@/components/auth-layout";

export const metadata: Metadata = { title: "注册" };

export default function RegisterPage() {
  return <AuthLayout><Suspense><AuthForm mode="register" /></Suspense></AuthLayout>;
}
