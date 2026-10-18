import { ApiRequestError, apiRequest, getServerSessionCredential } from "../api";

/** Distinguish an unverified cookie owner from a failed resource request. */
export class PrivateOwnerVerificationError extends ApiRequestError {}

async function verifyOwner(ownerId: string, signal?: AbortSignal) {
  try {
    const timeout = AbortSignal.timeout(30000);
    const user = await apiRequest<{ id: number }>("/auth/me/", {
      cache: "no-store", signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    }, getServerSessionCredential());
    if (!ownerId || String(user.id) !== ownerId) {
      throw new PrivateOwnerVerificationError("登录账户已变化，请重新读取当前账户的资料。", 403);
    }
  } catch (reason) {
    if (reason instanceof PrivateOwnerVerificationError) throw reason;
    throw new PrivateOwnerVerificationError(
      reason instanceof Error ? reason.message : "登录账户暂时无法验证，请重试。",
      reason instanceof ApiRequestError ? reason.status : 0,
    );
  }
}

/** A cookie can change in another tab without changing the caller's owner prop. */
export async function withPrivateOwner<T>(ownerId: string, action: () => Promise<T>, signal?: AbortSignal): Promise<T> {
  await verifyOwner(ownerId, signal);
  signal?.throwIfAborted();
  const result = await action();
  await verifyOwner(ownerId, signal);
  signal?.throwIfAborted();
  return result;
}
