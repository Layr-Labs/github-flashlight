# EigenDA Quick Reference

**Generated**: 2026-04-10 | **Source**: https://github.com/Layr-Labs/eigenda | **Commit**: 61019b4e9f91cbbb3dc05ed758674e4bdfeee20e

---

## What EigenDA Does

EigenDA is a decentralized data availability (DA) layer built on EigenLayer that allows rollups (Optimism, Arbitrum) to post blob data off Ethereum mainnet calldata, reducing costs while preserving security. Rollup batchers POST blobs to the EigenDA Proxy sidecar; the system erasure-codes each blob using KZG polynomial commitments + Reed-Solomon into chunks, fans them out to registered DA node operators, collects BLS multi-signatures attesting storage, and returns a certificate to the rollup. During the challenge window, anyone can retrieve the original blob via its certificate. The security guarantee — that enough chunks exist to reconstruct the blob — is backed by restaked ETH through EigenLayer's cryptoeconomic model.

---

## Key Components

### Go Services (Deployable Binaries)

| Service | Path | Role |
|---------|------|------|
| `api-server` | `api/proxy/cmd/server/` | Rollup-facing HTTP sidecar (OP-stack ALT-DA + Arbitrum Nitro Custom DA). Disperses blobs to EigenDA, retrieves + verifies on GET. |
| `disperser-apiserver` | `disperser/cmd/apiserver/` | External-facing gRPC ingest for v2 blobs. Validates, stores S3+DynamoDB, delegates payment to controller. |
| `disperser-controller` | `disperser/cmd/controller/` | v2 pipeline orchestrator: EncodingManager, batch assembly, StoreChunks fan-out, BLS aggregation, payment authorization. |
| `disperser-encoder` | `disperser/cmd/encoder/` | KZG/RS encoding gRPC service. v1: inline bytes; v2: S3 fetch-encode-store. GPU (Icicle) optional. |
| `disperser-batcher` | `disperser/cmd/batcher/` | v1 legacy pipeline: encodes, disperses, aggregates BLS sigs, submits on-chain `confirmBatch`. |
| `disperser-blobapi` | `disperser/cmd/blobapi/` | Combined DispersalServerV2 + Relay in one process for simplified deployment. |
| `disperser-dataapi` | `disperser/cmd/dataapi/` | Read-only observability HTTP API (blob/batch/operator/payment/metrics). |

### Go Libraries

| Library | Path | Role |
|---------|------|------|
| `core` | `core/` | Central domain model: types, BLS BN254 crypto, signature aggregation, chunk assignment, shard validation, Ethereum bindings, payment metering |
| `encoding` | `encoding/` | KZG + Reed-Solomon engine: FFT, committer, FK20 prover, universal batch verifier, Gnark/Icicle backends |
| `disperser` | `disperser/` | Dispersal subsystem library: v1 Batcher, v2 Controller/EncodingManager, BlobMetadataStore (DynamoDB), DataAPI |
| `relay` | `relay/` | Relay gRPC server: S3-backed blob/chunk serving, LRU caches, two-level rate limiting, BLS auth |
| `node` | `node/` | DA validator node: StoreChunks handler, LittDB storage, payment validation, EjectionSentinel |
| `litt` | `litt/` | LittDB: custom append-only KV store for DA node chunks (TTL, sharding, LRU caches, GC) |
| `common` | `common/` | Shared utilities: EthClient (multi-homing), AWS DynamoDB/S3/KMS, rate limiting, replay guard, logging |
| `api` | `api/` | Protobuf/gRPC generated code and typed client/server wrappers for all protocols |

### Solidity Contract Groups

| Group | Path | Key Contracts |
|-------|------|---------------|
| `core` | `contracts/src/core/` | EigenDAServiceManager (v1 confirmBatch), PaymentVault, EigenDADirectory (V3 service registry), EigenDAThresholdRegistry, EigenDARelayRegistry, EigenDADisperserRegistry, EigenDARegistryCoordinator |
| `integrations` | `contracts/src/integrations/` | EigenDACertVerifier (V4, immutable), EigenDACertVerifierRouter (ABN dispatch), legacy V1/V2 verifiers |
| `periphery` | `contracts/src/periphery/` | EigenDAEjectionManager (3-phase ejection: start/cancel/complete) |

### Rust Crates

| Crate | Path | Role |
|-------|------|------|
| `eigenda-srs-data` | `rust/crates/eigenda-srs-data/` | Compile-time embedded KZG SRS: 524,288 BN254 G1 points (~16 MiB), zero-copy `LazyLock<SRS>` |
| `eigenda-verification` | `rust/crates/eigenda-verification/` | Pure synchronous cert+blob verification: Merkle, BLS pairing, KZG recomputation. For op-reth, RISC0. |
| `eigenda-ethereum` | `rust/crates/eigenda-ethereum/` | Async Ethereum bridge: 8 parallel `eth_getProof` calls → `CertStateData` for verification |
| `eigenda-proxy` | `rust/crates/eigenda-proxy/` | Rust HTTP client for Go api-server (store_payload / get_encoded_payload) |
| `eigenda-tests` | `rust/crates/eigenda-tests/` | E2E test harness with Anvil local Ethereum via testcontainers |

---

## Main Data Flows

### V2 Dispersal (Modern Pipeline)
```
Rollup Batcher
  → POST /put → api-server (EigenDA Proxy)
  → gRPC DisperseBlob → disperser-apiserver
      → gRPC AuthorizePayment → disperser-controller (payment validated)
      → S3: StoreBlob(blobKey, raw bytes)
      → DynamoDB: PutBlobMetadata(status=Queued)
  ← blobKey returned

  [Background — EncodingManager polling DynamoDB every 2s]
  disperser-controller
      → gRPC EncodeBlob(blobKey) → disperser-encoder
          → S3: GetBlob + KZG/RS encode + S3: PutProofs+Coefficients
      → DynamoDB: PutBlobCertificate, UpdateStatus(Queued→Encoded)

  [Background — Controller dispatcher]
  disperser-controller
      → BuildMerkleTree(encoded blobs) → DynamoDB: PutBatchHeader+Inclusions
      → UpdateStatus(Encoded→GatheringSignatures)
      → fan-out gRPC StoreChunks → DA Validator Nodes (N)
          → each node: auth + payment + relay download + KZG verify + LittDB store → BLS sig
      → aggregate BLS sigs → DynamoDB: PutAttestation, UpdateStatus(→Complete)

  [api-server polling GetBlobStatus]
  api-server → EigenDACert (RLP) → Rollup Batcher
```

### V1 Dispersal (Legacy Batcher)
```
Client → DynamoDB: StoreBlob(status=Processing) + S3: UploadBlob
  [EncodingStreamer every 2s] → gRPC EncodeBlob(rawBytes) → disperser-encoder (inline)
  [Batcher loop] → CreateBatch → fan-out StoreChunks to operators → aggregate BLS sigs
  → eth-tx: EigenDAServiceManager.confirmBatch() → BatchConfirmed event
  → DynamoDB: MarkConfirmed / MarkFinalized (Finalizer checks every 6min)
```

### Blob Retrieval
```
Rollup Derivation
  → GET /get/{cert_hex}?l1_inclusion_block_number=N → api-server
  → eth_call checkDACert(cert) → EigenDACertVerifierRouter → EigenDACertVerifier (V4)
  → [V4 only] verify certRBN < L1IBN <= certRBN + windowSize
  → Try S3 secondary cache (keccak256(cert) → payload)
  → [cache miss] gRPC GetBlob(blobKey) → relay → S3 → payload
  → 200 OK raw payload bytes
  [418 Teapot = invalid cert — discard; 503 = failover to Ethereum DA]
```

### Off-Chain Cert Verification (Rust SDK)
```rust
// 1. Resolve contract addresses from EigenDADirectory
let provider = EigenDaProvider::new(config, signer).await?;

// 2. Fetch 8 parallel eth_getProof calls
let cert_state = provider.fetch_cert_state(block_height, &cert).await?;

// 3. Verify recency + storage proofs + BLS + KZG, decode payload
match verify_and_extract_payload(&tx, &cert, &cert_state, &state_root,
                                 &heights, recency_window, &encoded_payload) {
    Some(Ok(payload)) => { /* use */ }
    None => { /* stale cert, discard */ }
    Some(Err(e)) => { /* verification failed */ }
}
```

---

## Technology Choices

| Concern | Choice | Rationale |
|---------|--------|-----------|
| Inter-service communication | gRPC | Strong typing, streaming, multiplexing |
| Blob metadata | AWS DynamoDB | Serverless, conditional writes for state machine, GSI for status scans |
| Blob storage | AWS S3 | Scalable object store; partial range download for chunk subsetting |
| Tx signing (prod) | AWS KMS | Hardware key custody vs. plaintext hex private key in dev |
| Operator state indexing | The Graph (GraphQL subgraphs) | Avoid raw log scanning; 3 subgraphs for operator state, batch metadata, payments |
| Chunk encoding | KZG + Reed-Solomon on BN254 | Polynomial commitments match Ethereum's BN254 precompile; FK20 amortized multi-proofs |
| GPU acceleration | Icicle (CUDA 12.2.2) | 10-100x speedup for KZG/RS encoding; same interface as CPU Gnark backend |
| DA node storage | LittDB (custom) | Write-once/read-many workload; append-only, TTL GC, sharding; lower latency than general KV |
| Rust verification | arkworks (BN254) + rust-kzg-bn254 | Matches Go gnark-crypto behavior; synchronous for ZK-VM embedding; arkworks is audited |
| SRS distribution | Compile-time embedding in `eigenda-srs-data` | Zero I/O, zero-copy, guaranteed integrity; trade-off: 16 MiB binary inflation |

---

## Critical External Dependencies

| Dependency | Used by | Impact if unavailable |
|------------|---------|----------------------|
| **AWS DynamoDB** | disperser-apiserver, disperser-controller, disperser-batcher, disperser-blobapi, disperser-dataapi | Complete dispersal pipeline stops; no blob ingest or state tracking |
| **AWS S3** | disperser-apiserver, disperser-encoder, relay, api-server | Cannot store/retrieve blobs or encoded chunks |
| **AWS KMS** | disperser-batcher (production) | Cannot sign `confirmBatch` transactions (v1 only); swap to plaintext key as emergency fallback |
| **Ethereum RPC** | All services + eigenda-ethereum (Rust) | Cannot verify cert on-chain, cannot read operator state, cannot submit v1 confirmBatch |
| **The Graph** | disperser-controller, disperser-batcher, relay, disperser-dataapi | Cannot resolve indexed operator state (BLS keys, quorum membership, sockets). **Mandatory for batcher** — no fallback in v1. Controller has BatchMetadataManager with 75-block refresh buffer. |
| **EigenDADirectory (on-chain)** | eigenda-ethereum Rust crate at startup | Cannot resolve contract addresses for cert verification (cached after startup) |
| **EigenDACertVerifierRouter** | api-server (retrieval path) | Cannot verify certs on-chain; proxy will return 418/503 on all GETs |

### Dependency Resilience Notes
- **Multi-homing Ethereum RPC**: `MultiHomingClient` provides round-robin failover across multiple configured RPC endpoints with linear-backoff retry
- **TheGraph outage**: Controller has a 75-block buffered operator state snapshot; batcher has no fallback (TheGraph is mandatory). A TheGraph outage would halt v1 batch creation after the LRU cache expires.
- **DynamoDB partition limits**: At high throughput, the StatusIndex GSI can become a hot partition during `Queued` blob scans. Monitor consumed capacity units.
- **S3 resilience**: Standard S3 multipart upload with automatic retry; OCI-compatible alternative available for Oracle Cloud deployments

---

## Quick Orientation for New Developers

**"Where does a blob go?"**
1. Client calls `DisperseBlob` gRPC → `disperser/apiserver/server_v2.go` (`DispersalServerV2.DisperseBlob`)
2. Blob bytes land in S3; metadata in DynamoDB with status `Queued`
3. `disperser/controller/encoding_manager.go` picks it up, calls encoder, writes certificate → status `Encoded`
4. `disperser/controller/controller.go` assembles batch, fans out StoreChunks to DA nodes → status `GatheringSignatures`
5. `disperser/controller/signature_receiver.go` aggregates BLS sigs → status `Complete`
6. Client polls `GetBlobStatus` → receives `SignedBatch` + `BlobInclusionInfo` = the certificate

**"Where is BLS verification?"** → `core/aggregation.go` (Go, production dispersal), `rust/crates/eigenda-verification/src/verification/cert/` (Rust, rollup derivation)

**"Where is KZG encoding?"** → `encoding/v2/kzg/prover/` (FK20 multi-proof generation), called via gRPC by disperser-controller from `disperser/encoder/server_v2.go`

**"Where is chunk storage on DA nodes?"** → `litt/` (LittDB), accessed via `node/validator_store.go`

**"How does api-server know a cert is valid?"** → `eth_call` to `EigenDACertVerifierRouter` → `EigenDACertVerifier.checkDACert()` → returns uint8 status code (never reverts)
