import os
import logging
import traceback
import json
from flask import Flask, request, jsonify
from eth_account.messages import encode_defunct, encode_typed_data
from eth_account import Account
from eth_account.signers.local import LocalAccount
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load private key from environment variable
private_key = os.environ.get("CLIENT_PRIVATE_KEY")
if not private_key:
    raise ValueError(
        "CLIENT_PRIVATE_KEY environment variable not set. Make sure you have a .env file with this variable set."
    )

account: LocalAccount = Account.from_key(private_key)


@app.route("/address", methods=["GET"])
def get_address():
    """Returns the public address of the wallet."""
    return jsonify({"address": account.address})


@app.route("/sign", methods=["POST"])
def sign_payload():
    """
    Signs a payload. It can handle both standard string payloads (for mandates)
    and EIP-712 typed data payloads (for transactions).
    """
    try:
        payload = request.get_json()
        logger.info(f"Received request data: {json.dumps(payload, indent=2)}")

        if not payload:
            logger.error("Payload not provided in request.")
            return jsonify({"error": "Payload not provided"}), 400

        # Check if the payload is structured for EIP-712 signing
        if isinstance(payload, dict) and all(
            key in payload for key in ["types", "domain", "message", "primaryType"]
        ):
            logger.info("Attempting EIP-712 signing...")
            # Explicitly encode the typed data to get the signable hash
            signable_message = encode_typed_data(full_message=payload)
            # Sign the hash
            signed_message = account.sign_message(signable_message)
            signature = signed_message.signature.hex()
            logger.info(f"EIP-712 signing successful. Signature: {signature}")
            return jsonify({"signature": signature, "address": account.address})
        else:
            # This branch handles signing simple string/JSON payloads (for mandates)
            logger.info("Attempting standard string signing...")
            # The payload for mandates might be nested, so extract it.
            actual_payload = payload.get("payload", payload)
            payload_str = (
                json.dumps(actual_payload)
                if isinstance(actual_payload, dict)
                else actual_payload
            )
            message = encode_defunct(text=payload_str)
            signed_message = account.sign_message(message)
            signature = signed_message.signature.hex()
            logger.info(f"Standard signing successful. Signature: {signature}")
            return jsonify({"signature": signature, "address": account.address})

    except Exception as e:
        logger.error(f"An error occurred in /sign endpoint: {e}")
        logger.error(traceback.format_exc())  # Log the full traceback
        return jsonify({"error": "Internal server error during signing."}), 500


if __name__ == "__main__":
    app.run(host="localhost", port=5001)
