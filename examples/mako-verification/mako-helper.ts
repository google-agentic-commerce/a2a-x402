/**
 * Thin MAKO Verifier helper. Wraps the @pollinate/mako SDK.
 */

import { MakoClient, type VerifyRequest, type VerifyResponse } from "@pollinate/mako";
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";

let _mako: MakoClient | null = null;

function getMakoClient(): MakoClient {
  if (_mako) return _mako;
  const pk = process.env.AGENT_PRIVATE_KEY as `0x${string}` | undefined;
  if (!pk) throw new Error("Set AGENT_PRIVATE_KEY=0x... in env");
  const wallet = createWalletClient({
    account: privateKeyToAccount(pk),
    chain: base,
    transport: http(process.env.BASE_RPC_URL),
  });
  _mako = new MakoClient({ wallet });
  return _mako;
}

export async function verifyTargetWithMako(req: VerifyRequest): Promise<VerifyResponse> {
  return getMakoClient().verify(req);
}
