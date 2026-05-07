/**
 * A2A buyer agent that pre-verifies any payment target via MAKO before signing.
 *
 * The "A2A x402 flow" simulated here is intentionally minimal — production
 * integrations should use the official A2A SDK for the conversation transport.
 */

import { verifyTargetWithMako } from "./mako-helper.js";

interface A2APaymentRequiredAction {
  type: "paymentRequired";
  target_url: string;
  intended_task: string;
  max_price_usdc: number;
}

async function handleA2APayment(action: A2APaymentRequiredAction) {
  console.log(`A2A payment requested → ${action.target_url}`);

  const verdict = await verifyTargetWithMako({
    target_url: action.target_url,
    intended_task: action.intended_task,
    max_price_usdc: action.max_price_usdc,
    risk_mode: "strict",
  });

  if (verdict.verdict !== "callable" || verdict.score < 70) {
    console.warn("MAKO blocked the call:");
    for (const w of verdict.warnings) console.warn(" -", w);
    return {
      type: "a2a_response",
      status: "blocked_by_verifier",
      reason: verdict.warnings.join("; ") || "verdict not callable",
      receipt: verdict.receipt,
    };
  }

  console.log(`MAKO cleared the call (score ${verdict.score}). Proceeding.`);
  console.log("Recommended call plan:", verdict.call_plan);

  return {
    type: "a2a_response",
    status: "verified_and_ready",
    mako_score: verdict.score,
    mako_receipt: verdict.receipt,
  };
}

const inbound: A2APaymentRequiredAction = {
  type: "paymentRequired",
  target_url: process.env.TARGET_URL ?? "https://mako.pollinateresearch.com",
  intended_task: "Fetch latest governance proposal signal for arbitrumfoundation.eth",
  max_price_usdc: 0.10,
};

handleA2APayment(inbound)
  .then((result) => console.log("\nResponse:", JSON.stringify(result, null, 2)))
  .catch((err) => {
    console.error("Failed:", err);
    process.exit(1);
  });
