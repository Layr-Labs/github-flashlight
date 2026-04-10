# Ethereum RPC — Integration Analysis

**Classification**: external-service
**Application Type**: external-service
**Location**: External — Ethereum JSON-RPC nodes (L1 Ethereum mainnet or compatible testnet); accessed via HTTP/WebSocket endpoints

## Architecture

Ethereum RPC is the foundational external dependency for EigenDA. Every core subsystem — the disperser batcher, the data-availability protocol layer, the API proxy, and individual operators — depends on the ability to read from and write to the Ethereum blockchain.

The integration has three distinct purposes:

1. **Transaction submission**: The disperser batcher writes `ConfirmBatch` transactions to `EigenDAServiceManager` on-chain to finalize batches of data-availability proofs. Operators register/deregister via `RegistryCoordinator`. The disperser registry manager can update `EigenDADisperserRegistry`.

2. **Chain state queries**: The `core/eth` package implements a rich read layer across 15+ contracts. This covers operator stake weights, quorum membership, payment balances, blob version parameters, socket registrations, and security thresholds. These reads are pinned to specific block numbers to maintain consistency during batch assembly.

3. **Certificate verification**: The API proxy's `CertVerifier` uses `eth_call` to simulate `checkDACert` against the `EigenDACertVerifier` or `EigenDACertVerifierRouter` contracts without submitting a transaction, proving DA availability before a rollup derives a block.

Without Ethereum RPC access, EigenDA cannot confirm batches (batcher goes offline), cannot assemble correct quorum assignments (disperser/node breaks), and rollup derivation cannot verify DA certificates (proxy returns errors).

## Key Components

### `common/geth/` — 3-Tier Client Stack

Three concrete types implement the `common.EthClient` interface, layered by purpose:

**Tier 1 — `EthClient`** (`client.go`)
The raw client. Wraps `ethclient.Client` from go-ethereum. Holds a single `*ecdsa.PrivateKey`, a chain ID, and a confirmation count. Key methods:
- `GetLatestGasCaps`: calls `eth_maxPriorityFeePerGas` + `eth_getBlockByNumber`, then adds a 25% overage to the tip (with a fallback constant of 15 Gwei if the RPC does not support EIP-1559 priority fee queries).
- `UpdateGas`: re-estimates gas limit (`eth_estimateGas`) for a transaction and adds a 20% buffer.
- `EstimateGasPriceAndLimitAndSendTx`: combines gas estimation and `eth_sendRawTransaction` in one call, then blocks on `waitMined`.
- `waitMined`: polls `eth_getTransactionReceipt` every 3 seconds; only returns success once `receipt.BlockNumber + numConfirmations <= chainTip`.

**Tier 2 — `InstrumentedEthClient`** (`instrumented_client.go`)
Wraps `EthClient`. Every JSON-RPC call is wrapped by `instrumentFunction[T]`, which records a Prometheus counter (`rpc_calls_total`) and a histogram (`rpc_call_duration_seconds`) labelled by method name and `web3_clientVersion`. Conforms to the EigenLayer AVS node metrics specification.

**Tier 3 — `MultiHomingClient`** (`multihoming_client.go`)
Wraps a slice of `EthClient` instances — one per configured RPC URL — and implements the same interface. All 30+ `EthClient` methods are forwarded through an identical retry loop:

```go
for i := 0; i < m.NumRetries+1; i++ {
    m.sleepBeforeRetry(i)          // linear backoff: i * RetryDelay
    rpcIndex, instance := m.GetRPCInstance()
    result, err := instance.<Method>(...)
    if err == nil { return result, nil }
    if m.ProcessError(err, rpcIndex, "<Method>") { break }
}
```

`GetRPCInstance` selects the current endpoint by `totalFaults % len(RPCs)` — a simple round-robin triggered by fault count.

**`FailoverController`** (`failover.go`, `handle_error.go`)
Tracks a global `numberRpcFault` counter (atomically updated under a mutex). `ProcessError` classifies each error:
- HTTP 4xx (403, 429): rotate to next RPC and retry.
- HTTP 5xx: rotate and retry.
- JSON-RPC error code: rotate and immediately return (the RPC delivered a valid but negative response; retrying the same call on the same data is pointless).
- Connection / DNS / unknown: rotate and retry.

HTTP 2xx responses that contain a JSON-RPC error are treated as JSON-RPC errors, not HTTP errors.

**`SafeDial` / `SanitizeRpcUrl`** (`rpc_utils.go`)
All dial calls use `SafeDial`, which strips credentials from the URL before logging any connection errors. This prevents API keys embedded in RPC URLs (a common provider pattern) from appearing in logs.

### `core/eth/` — Contract Bindings and State Layer

**`ContractBindings`** struct (defined in `reader.go`) caches bound contract objects for every contract EigenDA interacts with:

| Field | Contract |
|---|---|
| `EigenDAServiceManager` | Batch confirmation, blob params, quorum thresholds |
| `RegistryCoordinator` | Operator registration/deregistration/churn |
| `OpStateRetriever` | Batch operator state and quorum bitmaps |
| `BLSApkRegistry` | Operator ID ↔ address resolution |
| `StakeRegistry` | Per-operator per-quorum stake weights |
| `IndexRegistry` | Operator count per quorum |
| `SocketRegistry` | Operator gRPC socket strings |
| `EjectionManager` | Forced operator ejection |
| `AVSDirectory` | AVS registration digest for ECDSA signing |
| `PaymentVault` | Reserved and on-demand payment balances |
| `ThresholdRegistry` | Blob version parameters |
| `DisperserRegistry` | Disperser address → ID mapping |
| `EigenDADirectory` | Contract address discovery |

**`Reader`** implements `core.Reader`. All read methods use `&bind.CallOpts{Context: ctx, BlockNumber: ...}` to pin queries to a specific block. The block number is typically the reference block number chosen for a batch, ensuring consistent operator state across a dispersal round.

**`Writer`** embeds `*Reader` and adds state-mutating transactions: `ConfirmBatch`, `RegisterOperator`, `RegisterOperatorWithChurn`, `DeregisterOperator`, `UpdateOperatorSocket`, `SetDisperserAddress`.

**`ChainState`** (`state.go`) wraps a `Reader` and an `EthClient`. It provides higher-level methods used by the disperser (e.g., `GetOperatorState`, `GetCurrentBlockNumber`) that translate raw contract call results into typed EigenDA domain objects.

**`ContractDirectory`** (`directory/contract_directory.go`)
A read-only wrapper around the `IEigenDADirectory` on-chain contract. It resolves canonical contract names (e.g., `"CERT_VERIFIER_ROUTER"`, `"SERVICE_MANAGER"`) to their current deployed addresses via `eth_call` to `GetAddress0`. Results are cached in a `sync.Map` (fetched once per address per process lifetime). This is used by the proxy and other consumers that do not want to hard-code contract addresses in config.

**`ReferenceBlockProvider`** (`reference_block_provider.go`)
Calls `eth_getBlockByNumber` (latest) and subtracts a configurable offset to hedge against forks. A monotonicity guard prevents the reference block number from going backward within a process run. A `periodicReferenceBlockProvider` wrapper throttles RPC calls by caching the value for a configurable update period.

**`QuorumScanner`** (`quorum_scanner.go`)
Reads `RegistryCoordinator.QuorumCount` at a given block number to enumerate active quorums. An LRU-cached variant avoids redundant calls for the same block.

### `disperser/batcher/` — Transaction Manager and Finalizer

**`txnManager`** (`txn_manager.go`)
The batcher's transaction lifecycle manager. It operates as a goroutine reading from a `requestChan`. For each transaction:

1. Calls `ethClient.GetLatestGasCaps` + `ethClient.UpdateGas` to compute current EIP-1559 prices.
2. Sends the transaction via `wallet.SendTransaction` (delegating signing to the wallet abstraction).
3. If the network times out at broadcast (Fireblocks latency), cancels the pending transaction via the Fireblocks API.
4. Polls receipt via `wallet.GetTransactionReceipt` every 3 seconds.
5. If no receipt within `txnRefreshInterval`, calls `speedUpTxn`: bumps gas price by 10% (or matches current network price, whichever is higher) and resubmits with the same nonce.
6. Waits for `numConfirmations` blocks beyond the mined block.
7. Emits the result on `receiptChan`.

**`finalizer`** (`finalizer.go`)
Runs periodically to transition blobs from `Confirmed` to `Finalized` state. Uses a raw `RPCEthClient.CallContext` to call `eth_getBlockByNumber` with the `"finalized"` block tag (which is an Ethereum beacon-chain feature, not available in all standard RPC methods). For each confirmed blob it:
1. Fetches the latest finalized block number.
2. Looks up the original confirmation transaction by hash (`eth_getTransactionReceipt`).
3. Detects reorgs: if the transaction's block number changed, updates the stored confirmation block number.
4. Marks the blob finalized only if its confirmation block is at or below the finalized block.
5. If the transaction hash is not found at all (i.e., reorged out permanently), marks the blob failed.

### `api/clients/v2/verification/` — Certificate Verifier

**`CertVerifier`** (`cert_verifier.go`)
Verifies EigenDA certificates by simulating a `checkDACert` view function call against the appropriate `EigenDACertVerifier` contract. This uses `eth_call` (read-only, no gas cost, no state change). The verifier:
1. ABI-encodes the certificate bytes using a pre-parsed binding (`v2VerifierBinding.TryPackCheckDACert`).
2. Calls `ethClient.CallContract` with the encoded data.
3. Unpacks and interprets the return value as a status code enum.
4. Returns `nil` for `StatusSuccess`, structured error types for invalid certs or internal failures.

Contract-level metadata (required quorums, confirmation threshold, cert version, offchain derivation version) is fetched once on first use per contract address and cached in `sync.Map` instances.

**`RouterAddressProvider`** (`router_cert_verifier_address_provider.go`)
Resolves which verifier contract address to use for a given reference block number by calling `EigenDACertVerifierRouter.GetCertVerifierAt`. Waits for the local RPC client to reach the target block number before issuing the call, preventing stale-state verification.

**`BlockNumberMonitor`** (`block_number_monitor.go`)
Polls `ethClient.BlockNumber` every second. Uses an atomic integer so that multiple concurrent goroutines waiting on the same block only trigger one poll at a time. Used by `RouterAddressProvider` to synchronize cert verification with chain head.

## System Flows

### Batch Confirmation (Disperser Batcher)

```
Batcher.HandleSingleBatch()
  |
  |-- Writer.BuildConfirmBatchTxn()
  |     |-- OpStateRetriever.GetCheckSignaturesIndices()  [eth_call]
  |     |-- EigenDAServiceManager.ConfirmBatch(NoSend)   [eth_call, builds tx]
  |
  |-- TxnManager.ProcessTransaction()
  |     |-- ethClient.GetLatestGasCaps()                 [eth_maxPriorityFeePerGas + eth_getBlockByNumber]
  |     |-- ethClient.UpdateGas()                        [eth_estimateGas]
  |     |-- wallet.SendTransaction()                     [eth_sendRawTransaction]
  |
  |-- TxnManager.monitorTransaction() [goroutine]
        |-- (loop every 3s) wallet.GetTransactionReceipt() [eth_getTransactionReceipt]
        |-- ethClient.BlockNumber()                        [eth_blockNumber]
        |-- (on timeout) speedUpTxn()
        |     |-- ethClient.GetLatestGasCaps()
        |     |-- ethClient.UpdateGas()
        |     |-- wallet.SendTransaction()
        |-- (on confirmation) emit to receiptChan
```

### Finality Tracking (Disperser Finalizer)

```
Finalizer.FinalizeBlobs() [runs on timer]
  |
  |-- rpcClient.CallContext("eth_getBlockByNumber", "finalized") [raw RPC]
  |
  |-- (for each confirmed blob)
        |-- ethClient.TransactionReceipt()  [eth_getTransactionReceipt]
        |-- (if block number changed) blobStore.UpdateConfirmationBlockNumber()
        |-- (if tx not found) blobStore.MarkBlobFailed()
        |-- (if block <= finalized) blobStore.MarkBlobFinalized()
```

### Certificate Verification (API Proxy)

```
Store.VerifyCert()
  |
  |-- CertVerifier.CheckDACert()
  |     |-- RouterAddressProvider.GetCertVerifierAddress()
  |     |     |-- BlockNumberMonitor.WaitForBlockNumber()   [eth_blockNumber, polling]
  |     |     |-- EigenDACertVerifierRouter.GetCertVerifierAt() [eth_call]
  |     |-- ethClient.CallContract(checkDACert calldata)    [eth_call]
  |     |-- interpret status code
  |
  |-- (for V4 certs) offchain derivation version check
        |-- CertVerifier.GetOffchainDerivationVersion()    [eth_call, cached]
        |-- verifyCertRBNRecencyCheck()                    [pure computation]
```

### Operator Registration (Node)

```
Writer.RegisterOperator()
  |
  |-- RegistryCoordinator.PubkeyRegistrationMessageHash()  [eth_call]
  |-- blsSigner.SignG1()                                   [local crypto]
  |-- AVSDirectory.CalculateOperatorAVSRegistrationDigestHash() [eth_call]
  |-- crypto.Sign(ecdsaPrivateKey)                         [local crypto]
  |-- RegistryCoordinator.RegisterOperator(NoSend)         [eth_call, builds tx]
  |-- ethClient.EstimateGasPriceAndLimitAndSendTx()
        |-- eth_maxPriorityFeePerGas
        |-- eth_getBlockByNumber
        |-- eth_estimateGas
        |-- eth_sendRawTransaction
        |-- (poll) eth_getTransactionReceipt
```

## External Dependencies

| Library | Version in `go.mod` | Role |
|---|---|---|
| `github.com/ethereum/go-ethereum` | `v1.15.3` (replaced) | Core Ethereum types, ABI codec, `ethclient`, `bind`, `rpc` package |
| `github.com/ethereum-optimism/op-geth` | `v1.101511.1` | **Replaces** the canonical go-ethereum module at compile time via a `replace` directive |
| `github.com/ethereum-optimism/optimism` | `v1.13.1-...` (Layr-Labs fork) | OP stack libraries used in proxy and cert verification |
| `github.com/Layr-Labs/eigensdk-go` | `v0.2.0-beta.1...` | `wallet` abstraction, KMS signer, BLS signer, `rpccalls` Prometheus collector |
| `github.com/aws/aws-sdk-go-v2/service/kms` | `v1.31.0` | AWS KMS backing for ECDSA private key (batcher only) |

**Why op-geth instead of canonical go-ethereum:**
The `go.mod` comment notes this is required by the `ethereum-optimism/optimism` dependency. The `replace` directive pins the entire `github.com/ethereum/go-ethereum` module to `github.com/ethereum-optimism/op-geth v1.101511.1`, which is OP's maintained fork. This is a transitive requirement from the OP stack integration in the proxy and controller — both use optimism libraries that import op-geth types. The code comment acknowledges this as technical debt: "we should get rid of op dependencies altogether in our production code."

## API Surface

### Ethereum JSON-RPC Methods Called

| Method | Called By | Purpose |
|---|---|---|
| `eth_call` | `Reader` (all contract reads), `CertVerifier` | Contract state reads, cert verification simulation |
| `eth_sendRawTransaction` | `EthClient.SendTransaction`, `TxnManager` | Submit signed transactions |
| `eth_getTransactionReceipt` | `EthClient.waitMined`, `TxnManager`, `Finalizer` | Poll for transaction confirmation |
| `eth_blockNumber` | `ChainState`, `BlockNumberMonitor`, `waitMined` | Get current chain head |
| `eth_getBlockByNumber` | `ReferenceBlockProvider`, `getGasFeeCap`, `InstrumentedEthClient` | Fetch base fee for EIP-1559, get latest/finalized block |
| `eth_getBlockByNumber` (with `"finalized"` tag) | `Finalizer.getLatestFinalizedBlock` | Ethereum beacon-chain finality tracking |
| `eth_maxPriorityFeePerGas` | `EthClient.GetLatestGasCaps` | EIP-1559 tip cap estimation |
| `eth_estimateGas` | `EthClient.UpdateGas` | Gas limit estimation before send |
| `eth_chainId` | `EthClient` constructor | Chain ID validation at startup |
| `eth_getLogs` | `MultiHomingClient.FilterLogs` | Log filtering (used by indexer/event listeners) |
| `eth_subscribe` | `MultiHomingClient.SubscribeFilterLogs`, `SubscribeNewHead` | WebSocket event subscriptions |
| `eth_getBalance` | `MultiHomingClient.BalanceAt` | Balance queries |
| `eth_getTransactionCount` | `MultiHomingClient.NonceAt`, `PendingNonceAt` | Nonce management |
| `eth_getCode` | `MultiHomingClient.CodeAt` | Contract existence checks |
| `eth_feeHistory` | `MultiHomingClient.FeeHistory` | Historical fee data |
| `net_version` | `MultiHomingClient.NetworkID` | Network ID check |
| `web3_clientVersion` | `InstrumentedEthClient` constructor | Prometheus label population |

### Smart Contracts Called

| Contract | Methods Called | Called By |
|---|---|---|
| `EigenDAServiceManager` | `ConfirmBatch` (tx), `AvsDirectory`, `RegistryCoordinator`, `EigenDARelayRegistry`, `EigenDAThresholdRegistry`, `PaymentVault`, `EigenDADisperserRegistry`, `BLOCKSTALEMEASURE`, `STOREDURATIONBLOCKS`, `QuorumAdversaryThresholdPercentages`, `QuorumConfirmationThresholdPercentages`, `QuorumNumbersRequired`, `GetBlobParams` | `Writer`, `Reader` |
| `EigenDARegistryCoordinator` | `RegisterOperator` (tx), `RegisterOperatorWithChurn` (tx), `DeregisterOperator` (tx), `UpdateSocket` (tx), `GetCurrentQuorumBitmap`, `PubkeyRegistrationMessageHash`, `CalculateOperatorChurnApprovalDigestHash`, `GetOperatorSetParams`, `Ejector`, `BlsApkRegistry`, `IndexRegistry`, `StakeRegistry`, `SocketRegistry`, `QuorumCount` | `Writer`, `Reader` |
| `OperatorStateRetriever` | `GetOperatorState`, `GetOperatorState0`, `GetOperatorStateWithSocket`, `GetCheckSignaturesIndices`, `GetBatchOperatorFromId`, `GetBatchOperatorId`, `GetQuorumBitmapsAtBlockNumber` | `Reader` |
| `BLSApkRegistry` | `PubkeyHashToOperator`, `GetOperatorId` | `Reader` |
| `StakeRegistry` | `WeightOfOperatorForQuorum` | `Reader` |
| `IndexRegistry` | `TotalOperatorsForQuorum` | `Reader` |
| `SocketRegistry` | `GetOperatorSocket` | `Reader` |
| `EjectionManager` | `EjectOperators` (tx) | `Reader` |
| `AVSDirectory` | `CalculateOperatorAVSRegistrationDigestHash` | `Reader` (registration flow) |
| `PaymentVault` | `GetReservations`, `GetReservation`, `GetOnDemandTotalDeposits`, `GetOnDemandTotalDeposit`, `GlobalSymbolsPerPeriod`, `GlobalRatePeriodInterval`, `MinNumSymbols`, `PricePerSymbol`, `ReservationPeriodInterval` | `Reader` |
| `EigenDAThresholdRegistry` | `NextBlobVersion` | `Reader` |
| `EigenDADisperserRegistry` | `SetDisperserInfo` (tx), `DisperserKeyToAddress` | `Writer`, `Reader` |
| `IEigenDADirectory` | `GetAddress0`, `GetAllNames` | `ContractDirectory` |
| `EigenDACertVerifierRouter` | `GetCertVerifierAt` | `RouterAddressProvider` |
| `EigenDACertVerifier` | `checkDACert` (simulated via `eth_call`), `QuorumNumbersRequired`, `SecurityThresholds`, `CertVersion`, `OffchainDerivationVersion` | `CertVerifier` |

## Configuration

### `common/geth/` (all services that use Ethereum directly)

| Environment Variable | Flag | Default | Required | Description |
|---|---|---|---|---|
| `{PREFIX}_CHAIN_RPC` | `chain.rpc` | — | Yes | Comma-separated list of primary RPC URLs. Disperser/Batcher accept multiple; Node uses first only |
| `{PREFIX}_CHAIN_RPC_FALLBACK` | `chain.rpc_fallback` | `""` | No | Single fallback RPC URL appended to the list |
| `{PREFIX}_PRIVATE_KEY` | `chain.private-key` | — | Yes (non-KMS) | Hex-encoded ECDSA private key for transaction signing |
| `{PREFIX}_NUM_CONFIRMATIONS` | `chain.num-confirmations` | `0` | No | Block confirmations to wait before treating a receipt as final |
| `{PREFIX}_NUM_RETRIES` | `chain.num-retries` | `2` | No | Max RPC retry attempts per call |
| `{PREFIX}_RETRY_DELAY_INCREMENT` | `chain.retry-delay-increment` | `0s` | No | Base duration for linear backoff (`n * delay` on nth retry) |

The `{PREFIX}` is component-specific: `DISPERSER_SERVER`, `BATCHER`, `NODE`, `RETRIEVER`, etc.

### Batcher KMS wallet (AWS KMS signing)

| Environment Variable | Flag | Default | Required | Description |
|---|---|---|---|---|
| `BATCHER_KMS_KEY_ID` | `batcher.kms-key-id` | — | If KMS enabled | AWS KMS key ID holding the ECDSA private key |
| `BATCHER_KMS_KEY_REGION` | `batcher.kms-key-region` | — | If KMS enabled | AWS region where the KMS key lives |
| `BATCHER_KMS_KEY_DISABLE` | `batcher.kms-key-disable` | `false` | No | Set `true` to fall back to plaintext private key |

### API Proxy (EigenDA V2 backend)

| Environment Variable | Flag | Default | Required | Description |
|---|---|---|---|---|
| `EIGENDA_PROXY_EIGENDA_V2_ETH_RPC` | `eigenda.v2.eth-rpc` | — | Yes (V2 backend) | Single Ethereum RPC URL for cert verification |
| `EIGENDA_PROXY_EIGENDA_V2_ETH_RPC_RETRY_COUNT` | `eigenda.v2.eth-rpc-retry-count` | `1` | No | Retry count for Ethereum RPC calls in the proxy |
| `EIGENDA_PROXY_EIGENDA_V2_ETH_RPC_RETRY_DELAY_INCREMENT` | `eigenda.v2.eth-rpc-retry-delay-increment` | `1s` | No | Linear backoff increment for proxy RPC retries |

## Security Considerations

### Private Key Management

EigenDA supports two signing strategies for the batcher:

**AWS KMS (preferred in production)**: The ECDSA private key never leaves AWS KMS. The `signerv2.NewKMSSigner` implementation from `eigensdk-go` calls AWS KMS `Sign` API for every transaction. The key ID and region are passed via environment variable. The public key is fetched at startup to derive the wallet address. KMS is the default path; the `--batcher.kms-key-disable` flag must be explicitly set to fall back to a plaintext key.

**Plaintext private key (development/testing)**: `PrivateKeyString` in `EthClientConfig` is a hex string. The code comment in `cli.go` explicitly marks this for conversion to a `*secret.Secret` type as a TODO, acknowledging the current insecurity. The private key is loaded directly into memory via `crypto.HexToECDSA`.

Nodes (operators) use a separate key loading path (`ReadEthClientConfigRPCOnly`) that does not accept a private key flag at all — the node's signing key is loaded from an encrypted keystore file, not from the Ethereum client config.

### Credential-Safe Logging

All RPC URL logging is routed through `SanitizeRpcUrl`, which strips the path, query string, and user info from the URL before inclusion in log lines. This is specifically documented as a guard against API key leakage when keys are embedded in URLs (a pattern used by Alchemy, Infura, QuickNode, etc.).

### Transaction Integrity

The `waitMined` / `ensureAnyTransactionEvaled` loops verify `receipt.Status == 1` (EVM success) before returning a confirmation. A failed transaction (reverted on-chain) is surfaced as `ErrTransactionFailed` so callers can take appropriate action (mark the batch as failed, retry with corrected data).

The gas bump logic in `speedUpTxn` ensures that replacement transactions always exceed the original gas price by at least 10%, which satisfies Ethereum mempool replacement rules (which require at least a 10% bump). It also compares against current network conditions and takes the maximum, preventing replacement transactions from being stuck when the network fee floor rose.

### Reorg Handling

The `Finalizer` explicitly detects reorgs by re-fetching the block number of each confirmed transaction hash before marking it finalized. If the block number changed, the stored confirmation metadata is updated. If the transaction is no longer found at all (`ethereum.NotFound`), the blob is transitioned to `Failed` status rather than staying in a limbo `Confirmed` state.

The `ReferenceBlockProvider` applies a configurable `offset` (subtracted from the latest block number) to hedge against very recent blocks being reorganized out. Its monotonicity guard further ensures that a brief downward jitter in the reported block number does not cause the reference block number to go backwards, which would break operator state lookups.

### Chain ID Validation

At `EthClient` construction time, the client immediately calls `eth_chainId` and stores the result. This chain ID is passed to `bind.NewKeyedTransactorWithChainID` for EIP-155 replay-protection signing. A misconfigured RPC pointing at the wrong network will cause transaction signing to fail at submission time with a chain ID mismatch error.

### Failure Modes

- **RPC endpoint unreachable**: `MultiHomingClient` cycles through all configured endpoints up to `NumRetries` times. If all endpoints fail, the call returns the last error. The disperser batcher will fail to confirm batches; blobs remain in `InProgress` state until the next batch attempt.
- **All endpoints exhausted**: Logged at `Fatal` level by `GetRPCInstance` if no clients are available at construction time.
- **Finalized block tag unsupported**: The `Finalizer` uses `"finalized"` as the block tag, which requires a post-Merge Ethereum node or a compatible node software. Pre-Merge nodes or some testnets may return an error. Blobs would remain perpetually in `Confirmed` state if this call fails continuously.
- **Gas estimation failure**: `EstimateGasPriceAndLimitAndSendTx` returns the error directly; the batcher logs it and marks the batch as failed.
- **KMS API failure at signing time**: The `TxnManager` returns `ErrTransactionNotBroadcasted` after `txnBroadcastTimeout` and attempts to cancel pending Fireblocks transactions to unblock subsequent nonce progression.
