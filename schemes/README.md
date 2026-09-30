# Experimental Schemes

This directory contains experimental x402 payment schemes drafted by partners and other contributors.

These schemes are not yet part of the x402 specification; they are provided for reference and experimentation.

When ready, each scheme should be upstreamed to the [main x402 schemes repository](https://github.com/coinbase/x402/tree/main/specs/schemes) per the [contribution guidelines](https://github.com/coinbase/x402/blob/main/CONTRIBUTING.md#new-schemes).

## Available Schemes

| Scheme | Network | Description |
|--------|---------|-------------|
| [`exact_lightning`](scheme_exact_lightning.md) | Lightning | Bitcoin payments via BOLT11 invoices |
| [`exact_spark`](scheme_exact_spark.md) | Spark | Bitcoin payments via Lightning or Spark |
| [`exact_uma`](scheme_exact_uma.md) | UMA | Bitcoin payments via UMA addresses |
| [`provenance-notarization`](scheme_provenance_notarization.md) | Base + NEAR | Post-payment provenance — cryptographic proof-of-existence for agent outputs via notarized PDRs |
