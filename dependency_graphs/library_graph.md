# Library Dependency Graph

## Phase 1: Foundation Libraries (No Dependencies)

### `@eigenda/contracts`

- **Type**: javascript-package
- **Path**: `contracts`
- **Description**: EigenDA core contracts
- **Dependencies**: None
- **External Dependencies**: `@openzeppelin/contracts` (4.7.0), `@openzeppelin/contracts-upgradeable` (4.7.0)

### `clients`

- **Type**: go-module
- **Path**: `api/proxy/clients`
- **Dependencies**: None

### `crypto`

- **Type**: go-module
- **Path**: `crypto`
- **Dependencies**: None

### `eigenda-batch-metadata`

- **Type**: typescript-package
- **Path**: `subgraphs/eigenda-batch-metadata`
- **Dependencies**: None

### `eigenda-operator-state`

- **Type**: typescript-package
- **Path**: `subgraphs/eigenda-operator-state`
- **Dependencies**: None

### `eigenda-payments`

- **Type**: typescript-package
- **Path**: `subgraphs/eigenda-payments`
- **Dependencies**: None
- **External Dependencies**: `@graphprotocol/graph-cli` (0.97.1), `@graphprotocol/graph-ts` (0.37.0)

### `eigenda-srs-data`

- **Type**: rust-crate
- **Path**: `rust/crates/eigenda-srs-data`
- **Dependencies**: None
- **External Dependencies**: `ark-bn254`, `rust-kzg-bn254-prover`

### `eigenda-subgraphs`

- **Type**: typescript-package
- **Path**: `subgraphs`
- **Dependencies**: None
- **External Dependencies**: `@graphprotocol/graph-cli` (0.51.0), `@graphprotocol/graph-ts` (0.32.0)

### `eigenda-tests`

- **Type**: rust-crate
- **Path**: `rust/crates/eigenda-tests`
- **Dependencies**: None

## Phase 2: Dependent Libraries (Topological Order)

### `api`

- **Type**: go-module
- **Path**: `api`
- **Depends On**: `common`, `core`, `encoding`, `indexer`, `node`

### `common`

- **Type**: go-module
- **Path**: `common`
- **Depends On**: `core`, `disperser`, `ejector`, `encoding`, `litt`

### `core`

- **Type**: go-module
- **Path**: `core`
- **Depends On**: `api`, `common`, `encoding`, `indexer`

### `disperser`

- **Type**: go-module
- **Path**: `disperser`
- **Depends On**: `api`, `common`, `core`, `encoding`, `indexer`, `operators`, `relay`

### `eigenda-verification`

- **Type**: rust-crate
- **Path**: `rust/crates/eigenda-verification`
- **Depends On**: `eigenda-srs-data`
- **External Dependencies**: `alloy-consensus`, `alloy-primitives`, `alloy-rlp`, `alloy-sol-types`, `ark-bn254` (+14 more)

### `ejector`

- **Type**: go-module
- **Path**: `ejector`
- **Depends On**: `api`, `common`, `core`, `disperser`

### `encoding`

- **Type**: go-module
- **Path**: `encoding`
- **Depends On**: `api`, `common`, `core`, `crypto`

### `indexer`

- **Type**: go-module
- **Path**: `indexer`
- **Depends On**: `common`

### `litt`

- **Type**: go-module
- **Path**: `litt`
- **Depends On**: `common`, `core`

### `node`

- **Type**: go-module
- **Path**: `node`
- **Depends On**: `api`, `common`, `core`, `encoding`, `litt`, `operators`

### `operators`

- **Type**: go-module
- **Path**: `operators`
- **Depends On**: `api`, `common`, `core`, `indexer`, `node`

### `relay`

- **Type**: go-module
- **Path**: `relay`
- **Depends On**: `api`, `common`, `core`, `crypto`, `disperser`, `encoding`

### `eigenda-ethereum`

- **Type**: rust-crate
- **Path**: `rust/crates/eigenda-ethereum`
- **Depends On**: `eigenda-verification`
- **External Dependencies**: `alloy-consensus`, `alloy-contract`, `alloy-primitives`, `alloy-provider`, `alloy-rpc-client` (+10 more)

### `eigenda-proxy`

- **Type**: rust-crate
- **Path**: `rust/crates/eigenda-proxy`
- **Depends On**: `eigenda-verification`
- **External Dependencies**: `backon`, `bytes`, `hex`, `reqwest` (0.12.22), `serde` (+5 more)

### `retriever`

- **Type**: go-module
- **Path**: `retriever`
- **Depends On**: `api`, `common`, `core`, `encoding`

