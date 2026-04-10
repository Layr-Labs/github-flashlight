# AWS DynamoDB — Integration Analysis

**Classification**: external-service
**Application Type**: external-service
**Location**: External — AWS managed NoSQL database service; used as the primary metadata persistence layer for the EigenDA dispersal pipeline

## Architecture

DynamoDB is the spine of EigenDA's blob lifecycle tracking. Every blob accepted by the disperser is represented in DynamoDB throughout its entire journey — from initial receipt through encoding, dispersal to node operators, attestation collection, and final completion or failure. The service fills three distinct roles:

1. **Blob state machine store (v1 and v2)**: The `BlobMetadataStore` in both `disperser/common/blobstore/` (v1) and `disperser/common/v2/blobstore/` (v2) records blob metadata and enforces status transitions using conditional writes. No blob can jump to an invalid status; the constraint is encoded directly in the DynamoDB `UpdateItem` condition expression.

2. **Payment metering store**: Three separate tables track reservation usage (per-account per-time-window bin counters), on-demand cumulative payments (per-account monotonically increasing payment totals), and global reservation rate bins. Atomic `ADD` increments prevent double-counting under concurrent requests.

3. **Signing-rate persistence**: A dedicated `dynamoSigningRateStorage` in `core/signingrate/` stores serialized protobuf `SigningRateBucket` records keyed by start timestamp with a GSI over end timestamp, enabling efficient historical loads on controller restart.

Without DynamoDB, the disperser has no durable record of in-flight blobs. A restart would lose all blobs in the `Queued` or `Encoded` states, the controller's dispersal queue would be empty, and payment metering would have no cumulative-payment checkpoint to enforce monotonicity.

## Key Components

### `common/aws/dynamodb/client.go`
A shared, singleton wrapper (`Client` interface, `client` struct) around `*dynamodb.Client`. Constructed once via `sync.Once`. Provides every higher-level operation used across the codebase:

- `PutItem` / `PutItemWithCondition` / `PutItemWithConditionAndReturn`
- `PutItems` — batched writes in chunks of 25 (DynamoDB hard limit), returns unprocessed items
- `UpdateItem` / `UpdateItemWithCondition` — uses `expression.Builder` to build SET expressions; filters primary key attributes out of the update payload
- `IncrementBy` — atomic `ADD` on a numeric attribute, used for bin-usage counters
- `GetItem` / `GetItemWithInput` / `GetItems` — batched reads in chunks of 100
- `QueryIndex` / `Query` / `QueryWithInput` / `QueryIndexCount` / `QueryIndexWithPagination`
- `DeleteItem` / `DeleteItems` — batched deletes in chunks of 25
- `TableExists` — startup health check via `DescribeTable`

`ErrConditionFailed` is a package-level sentinel error mapped from `*types.ConditionalCheckFailedException`, allowing callers to detect optimistic-concurrency failures without inspecting the raw AWS error type.

The client is initialized with `aws.RetryModeStandard`, which means the AWS SDK applies exponential backoff with jitter for retriable errors (throttles, transient failures) automatically. No additional retry logic is layered on top in most paths; the one exception is `PutBlobInclusionInfos`, which adds an explicit 3-attempt loop with exponential sleep (1s, 2s, 4s) on top of SDK retries for batch writes that return unprocessed items.

### `disperser/common/v2/blobstore/dynamo_metadata_store.go` — v2 BlobMetadataStore
The primary v2 metadata store. Uses a single DynamoDB table with a composite PK/SK scheme. All entity types are co-located in the same table and distinguished by SK prefix. Key constants define all prefixes and GSI names. Constructed by `NewBlobMetadataStore`; wrapped by `NewInstrumentedMetadataStore` for Prometheus instrumentation.

### `disperser/common/blobstore/blob_metadata_store.go` — v1 BlobMetadataStore
Legacy v1 store, still used by the v1 `dataapi`. Uses a separate flat-key scheme: `BlobHash` (partition) + `MetadataHash` (sort). Three GSIs: `StatusIndex`, `BatchIndex`, `Status-Expiry-Index`.

### `core/meterer/dynamodb_metering_store.go`
`DynamoDBMeteringStore` — the original (now partially deprecated) payment metering store. Owns three separate table references: reservation bins, on-demand payments, and global-rate bins. Validates all three tables exist at construction time.

### `core/payments/ondemand/cumulative_payment_store.go`
`CumulativePaymentStore` — a newer, per-account scoped wrapper around `*dynamodb.Client` (the raw SDK client, not the wrapper). Performs unconditional `UpdateItem SET` to store cumulative payment and consistent `GetItem` to read it. Uses strongly consistent reads to avoid stale data.

### `core/payments/ondemand/ondemandvalidation/on_demand_ledger_cache.go`
`OnDemandLedgerCache` — LRU cache (configurable max size) of per-account `OnDemandLedger` objects. Each ledger is backed by a `CumulativePaymentStore`. Cache misses trigger a DynamoDB read of the existing cumulative payment and a PaymentVault RPC. A `OnDemandVaultMonitor` polls the vault on a configurable interval to refresh total-deposit values.

### `core/signingrate/dynamo_signing_rate_storage.go`
`dynamoSigningRateStorage` — stores and loads signing-rate time-bucket protobuf payloads. Uses `UpdateItem` for upsert semantics. On startup, calls `ensureTableExists` / `waitForTableActive` (polling every 2s, timeout 10min) and auto-creates the table and its GSI if absent. The GSI uses a constant dummy partition key (`partitionKeyValue = "X\``"`) to allow range queries over `EndTimestamp`.

### `disperser/controller/dynamodb_blob_dispersal_queue.go`
`dynamodbBlobDispersalQueue` — a goroutine that continuously polls DynamoDB for blobs in `Encoded` status using `GetBlobMetadataByStatusPaginated`, feeds them into a buffered channel, and passes them to the dispatcher. Includes a `ReplayGuardian` to suppress stale or future-dated blobs; marks those as `Failed` via a status update.

## System Flows

### Blob Ingestion (v2 API Server path)

```
Client gRPC → apiserver.DisperseBlobV2
  → BlobMetadataStore.PutBlobMetadata
      PutItemWithCondition("attribute_not_exists(PK) AND attribute_not_exists(SK)")
      [DynamoDB: creates BlobMetadata row, status=Queued]
  → BlobMetadataStore.UpdateAccount
      PutItem  [DynamoDB: upserts Account entry]
```

### Encoding and Dispersal

```
EncodingManager polls BlobMetadataStore.GetBlobMetadataByStatus(Queued)
  → DynamoDB: QueryIndex StatusIndex where BlobStatus=0 AND UpdatedAt>cursor
  → sends blobs to encoder
  → BlobMetadataStore.UpdateBlobStatus(Encoded)
      UpdateItemWithCondition: SET BlobStatus=1, condition: BlobStatus IN (0)
      [DynamoDB: conditional update, fails if not Queued]

dynamodbBlobDispersalQueue.fetchBlobs polls:
  → BlobMetadataStore.GetBlobMetadataByStatusPaginated(Encoded, cursor, batchSize)
      QueryIndexWithPagination StatusIndex where BlobStatus=1, ascending
  → BlobMetadataStore.UpdateBlobStatus(GatheringSignatures)
      UpdateItemWithCondition: condition BlobStatus IN (1)

Dispatcher sends chunks to node operators:
  → BlobMetadataStore.PutDispersalRequest
      PutItemWithCondition("attribute_not_exists(PK) AND attribute_not_exists(SK)")
  → BlobMetadataStore.PutDispersalResponse (per operator response)
      PutItemWithCondition (idempotency guard)

Signature receiver collects attestations:
  → BlobMetadataStore.PutAttestation (overwrite allowed, no condition)
  → BlobMetadataStore.UpdateBlobStatus(Complete)
      UpdateItemWithCondition: condition BlobStatus IN (2)  [GatheringSignatures]
  → BlobMetadataStore.PutBlobInclusionInfos (batch write, 3 retries)
```

### On-Demand Payment Authorization

```
apiserver.DisperseBlobV2 (payment check)
  → OnDemandLedgerCache.GetOrCreate(accountID)
      LRU hit → OnDemandLedger (already loaded)
      LRU miss → CumulativePaymentStore.GetCumulativePayment
                    GetItem(consistent=true) from on-demand table
               → OnDemandLedger.OnDemandLedgerFromStore
  → OnDemandLedger.AuthorizeDispersalRequest
  → CumulativePaymentStore.StoreCumulativePayment
      UpdateItem SET CumulativePayment = :newValue
```

### Reservation Bin Metering (legacy path via DynamoDBMeteringStore)

```
Meterer.UpdateReservationBin(accountID, period, size)
  → DynamoDBMeteringStore.UpdateReservationBin
      IncrementBy ADD BinUsage += size  (atomic)
Meterer.UpdateGlobalBin(period, size)
  → DynamoDBMeteringStore.UpdateGlobalBin
      IncrementBy ADD BinUsage += size  (atomic)
```

### Signing Rate Persistence

```
Controller stores new signing-rate buckets:
  → dynamoSigningRateStorage.StoreBuckets
      UpdateItem SET Payload, EndTimestamp, PartitionKey (upsert)

Controller restart / apiserver signing-rate scrape:
  → dynamoSigningRateStorage.LoadBuckets(startTime)
      Query EndTimestampIndex (GSI) where PartitionKey=const AND EndTimestamp > startTime
      Paginated until LastEvaluatedKey == nil
```

## External Dependencies

All DynamoDB access uses the AWS SDK v2 for Go:

| Package | Version | Usage |
|---|---|---|
| `github.com/aws/aws-sdk-go-v2` | v1.26.1 | Core SDK types, `aws.Endpoint`, retry modes |
| `github.com/aws/aws-sdk-go-v2/config` | v1.27.11 | `LoadDefaultConfig`, credential providers |
| `github.com/aws/aws-sdk-go-v2/credentials` | v1.17.11 | `NewStaticCredentialsProvider` for static key/secret |
| `github.com/aws/aws-sdk-go-v2/service/dynamodb` | v1.31.0 | `dynamodb.Client`, all operation input/output types |
| `github.com/aws/aws-sdk-go-v2/service/dynamodb/types` | (sub-package of above) | `AttributeValue` variants, `ConditionalCheckFailedException` |
| `github.com/aws/aws-sdk-go-v2/feature/dynamodb/attributevalue` | v1.13.12 | `MarshalMap` / `UnmarshalMap` for struct serialization |
| `github.com/aws/aws-sdk-go-v2/feature/dynamodb/expression` | v1.7.12 | `expression.Builder`, `ConditionBuilder`, `UpdateBuilder` |

The `dynamoSigningRateStorage` and `CumulativePaymentStore` use `*dynamodb.Client` directly rather than the wrapper, and store protobuf binary payloads serialized with `google.golang.org/protobuf/proto`.

## API Surface

All access goes through DynamoDB's standard HTTP-based API. The codebase consumes the following DynamoDB operations:

| Operation | Used by | Purpose |
|---|---|---|
| `GetItem` | BlobMetadataStore (v1, v2), DynamoDBMeteringStore, CumulativePaymentStore | Single-item point reads; attestation uses `ConsistentRead=true` |
| `PutItem` | BlobMetadataStore (v1, v2), DynamoDBMeteringStore, BlobMetadataStore.UpdateAccount | Unconditional write; attestation overwrite allowed |
| `PutItem` + `ConditionExpression` | BlobMetadataStore (v2 for metadata, cert, dispersal req/resp, batch header, inclusion), OnDemandPayment | Idempotency / insert-only guards; `attribute_not_exists(PK) AND attribute_not_exists(SK)` |
| `PutItem` + `ConditionExpression` + `ReturnValues=ALL_OLD` | DynamoDBMeteringStore.AddOnDemandPayment | Conditional upsert returning old item for rollback support |
| `UpdateItem` | BlobMetadataStore v1/v2, DynamoDBMeteringStore (IncrementBy), CumulativePaymentStore, dynamoSigningRateStorage | Conditional and unconditional updates |
| `UpdateItem` + `ConditionExpression` | BlobMetadataStore.UpdateBlobStatus (v2) | Enforces state machine transitions: `BlobStatus IN (validPriorStates)` |
| `BatchWriteItem` | BlobMetadataStore (PutItems, DeleteItems) | Up to 25 put/delete requests per call; unprocessed items collected and retried |
| `BatchGetItem` | BlobMetadataStore.GetItems (v2: GetBlobCertificates) | Up to 100 keys per call; optional `ConsistentRead` |
| `Query` | BlobMetadataStore (v1, v2), dynamoSigningRateStorage, DynamoDBMeteringStore.GetPeriodRecords | Key condition + optional filter expressions; all paginated variants use `ExclusiveStartKey` |
| `DescribeTable` | `client.TableExists`, `OnDemandLedgerCache`, `dynamoSigningRateStorage.ensureTableExists` | Startup health checks; `dynamoSigningRateStorage` also creates the table if absent |
| `CreateTable` | `dynamoSigningRateStorage` only | Auto-creates the signing-rate table with GSI if it does not exist |
| `DeleteTable` | Test utilities only | Cleanup in integration tests |

There are no DynamoDB Streams or callbacks; this integration is purely request/response.

## Configuration

All components consume `commonaws.ClientConfig` or read the same flags via `aws.ReadClientConfig`. The following environment variables are the canonical configuration surface (prefix varies by component):

**Shared AWS credentials and endpoint (all DynamoDB-using services):**

| Env Var | Required | Description |
|---|---|---|
| `<PREFIX>_AWS_REGION` | Yes | AWS region (e.g., `us-east-2`) |
| `<PREFIX>_AWS_ACCESS_KEY_ID` | No | Static access key ID; if omitted, the SDK's default credential chain is used (instance profile / ECS task role / env vars) |
| `<PREFIX>_AWS_SECRET_ACCESS_KEY` | No | Static secret key |
| `<PREFIX>_AWS_ENDPOINT_URL` | No | Custom endpoint URL; used for LocalStack in tests (`http://localhost:4566`) |

**v2 blob metadata table (apiserver, controller, dataapi, blobapi):**

| Env Var | Required | Description |
|---|---|---|
| `CONTROLLER_DYNAMODB_TABLE_NAME` | Yes (controller) | v2 blob metadata table name |
| `DISPERSER_SERVER_DYNAMODB_TABLE_NAME` | Yes (apiserver) | Same table, seen from the API server |

**Payment metering tables (apiserver only, when `EnablePaymentMeterer=true`):**

| Env Var | Description |
|---|---|
| `DISPERSER_SERVER_RESERVATIONS_TABLE_NAME` | Per-account reservation bin usage table |
| `DISPERSER_SERVER_ON_DEMAND_TABLE_NAME` | Per-account cumulative on-demand payment table |
| `DISPERSER_SERVER_GLOBAL_RATE_TABLE_NAME` | Global reservation rate bin table |

**Controller on-demand payments:**

| Env Var | Description |
|---|---|
| `CONTROLLER_ON_DEMAND_PAYMENTS_TABLE_NAME` | On-demand ledger table accessed by the controller payment authorization path |

**Signing-rate storage (controller):**

| Env Var | Description |
|---|---|
| `CONTROLLER_SIGNING_RATE_DYNAMODB_TABLE_NAME` | Table for signing-rate bucket persistence; auto-created at startup if absent |

In the integration test harness (`inabox`), default table names are `e2e_v2_reservation`, `e2e_v2_ondemand`, `e2e_v2_global_reservation`, and each test run points at a LocalStack instance via `AWS_ENDPOINT_URL=http://localhost:4566`.

## Security Considerations

**Authentication and credential management:**
- In production the client is expected to operate without static credentials (`AccessKey`/`SecretAccessKey` left empty), relying on the AWS SDK default credential chain — typically an EC2/ECS IAM role attached to the instance or task. This means no long-lived secrets need to be distributed to the service.
- When static credentials are configured (e.g., for local development or CI), they are passed as `credentials.NewStaticCredentialsProvider` and never logged. However, they are stored in plain-text Go structs; the codebase includes a TODO comment to replace `SecretAccessKey string` with `*secret.Secret`.
- The `common/aws/kms.go` and `common/aws/secretmanager/` packages exist for KMS signing (disperser request signing) and Secrets Manager, but are not used for DynamoDB credential retrieval.

**Conditional writes as a consistency mechanism:**
- All insert operations use `attribute_not_exists(PK) AND attribute_not_exists(SK)` to prevent duplicate records without application-level locking.
- All `UpdateBlobStatus` calls include a condition ensuring the current status is one of the valid predecessor states. A `ConditionalCheckFailedException` is translated to `ErrConditionFailed` and surfaced as `ErrInvalidStateTransition` or `ErrAlreadyExists`. This makes the blob state machine tamper-evident at the storage level.
- On-demand payment updates use a condition (`attribute_not_exists(CumulativePayment) OR CumulativePayment <= :checkpoint`) that ensures the stored value can only increase, preventing replay or rollback exploits.

**Consistent reads:**
- Attestation fetch (`GetAttestation`) and signed-batch fetch (`GetSignedBatch`) use `ConsistentRead: true` to prevent race conditions where a read could see a stale pre-write value for a recently finalized batch.
- `CumulativePaymentStore.GetCumulativePayment` also uses `ConsistentRead: true` to ensure payment authorization always sees the latest committed value.
- Most other reads use eventually consistent defaults, which is appropriate for feed/query operations where a few milliseconds of lag is tolerable.

**Failure modes:**
- A DynamoDB outage blocks all new blob ingestion (the API server's `PutBlobMetadata` call will fail) and halts the dispersal pipeline (the controller's `GetBlobMetadataByStatusPaginated` polling will error). Errors are propagated back to callers; there is no circuit-breaker or fallback storage.
- The `PutBlobInclusionInfos` path has an explicit 3-attempt retry with exponential back-off (1s, 2s, 4s) on unprocessed batch-write items; this is the only place the codebase supplements the SDK's standard retry mode with application-level retries.
- The singleton client (`sync.Once`) means a construction error (bad credentials, invalid region) will permanently break DynamoDB access for the lifetime of the process.
- The `dynamoSigningRateStorage` self-heals at startup by creating its table if absent (polling up to 10 minutes for `ACTIVE` status). No other table auto-creation logic exists; the other tables are expected to be pre-provisioned.

**Data sensitivity:**
- DynamoDB stores blob keys (SHA-256 hashes of blob headers), account Ethereum addresses, cumulative payment amounts in wei, and dispersal request/response metadata. Blob content is stored in S3, not DynamoDB.
- No PII or private keys are stored in DynamoDB. Operator IDs and account addresses are public Ethereum addresses.
