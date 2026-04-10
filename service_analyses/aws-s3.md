# AWS S3 (and S3-compatible storage) — Integration Analysis

**Classification**: external-service
**Application Type**: external-service
**Location**: External — AWS S3 object storage (or compatible: OCI Object Storage, MinIO/GCS via minio-go)

---

## Architecture

S3 is the durable, shared object store that holds all raw blob bytes and encoded chunk data in EigenDA. It is central to the dispersal pipeline: blobs arrive at the API server, are stored in S3, fetched by the encoder for KZG proof generation, and the resulting chunks/proofs are written back to S3. The relay then reads from S3 to serve `GetBlob` and `GetChunks` requests.

The codebase keeps a strict separation between metadata (held in DynamoDB) and payload (held in S3). Removing S3 would break the entire data availability path: blobs could not be dispersed, encoded, attested, or retrieved.

Two distinct integration tracks exist:

1. **Disperser track** (v1 and v2): raw blobs and encoded chunk/proof objects are stored in S3 buckets. A shared abstraction layer (`common/s3`) allows the same disperser and relay code to operate against either AWS S3 or Oracle Cloud Infrastructure (OCI) Object Storage, selected at startup via `--object-storage-backend`.

2. **Proxy track** (api-server / eigenda-proxy): S3 is used as an optional secondary store — as a read cache or read fallback — for OP-keccak commitments. This track uses `minio-go` rather than the AWS SDK, making it compatible with AWS S3, MinIO, GCS, and any other minio-compatible endpoint.

---

## Key Components

### `common/s3/` — shared interface and implementations

| File | Role |
|---|---|
| `common/s3/s3_client.go` | `S3Client` interface: `HeadObject`, `UploadObject`, `DownloadObject`, `DownloadPartialObject`, `DeleteObject`, `ListObjects`, `CreateBucket`. Also defines `ErrObjectNotFound` and `ListedObject`. |
| `common/s3/scoped_keys.go` | Key-namespacing helpers: `ScopedBlobKey`, `ScopedChunkKey`, `ScopedProofKey`. Generates 3-char prefix-partitioned paths. |
| `common/s3/aws/aws_s3_client.go` | AWS SDK v2 implementation. Singleton via `sync.Once`. Configurable endpoint URL (for LocalStack/MinIO override), region, and optional static credentials. Multipart transfers via `s3/manager`. |
| `common/s3/oci/oci_s3_client.go` | OCI Object Storage implementation behind the same `S3Client` interface. Authenticates with OKE Workload Identity. |
| `common/s3/mock_s3_client.go` | In-memory mock for unit tests. |

### `disperser/common/blobstore/` — factory and v1 store

| File | Role |
|---|---|
| `client_factory.go` | `CreateObjectStorageClient()` selects between `S3Backend` and `OCIBackend` at runtime. Passes `aws.ClientConfig` fields (region, keys, endpoint URL, parallelism) into the appropriate constructor. |
| `shared_storage.go` | v1 `SharedBlobStore`. Keys blobs as `blob/<sha256hex>.json`. Up to 64 parallel S3 fetches via `workerpool`. |

### `disperser/common/v2/blobstore/` — v2 blob store

| File | Role |
|---|---|
| `s3_blob_store.go` | v2 `BlobStore`. Uses `ScopedBlobKey` for writes/reads. Deduplicates on `HeadObject` before `UploadObject`. |

### `relay/chunkstore/` — chunk and proof store

| File | Role |
|---|---|
| `chunk_writer.go` | `ChunkWriter` — writes KZG proofs (`ScopedProofKey`) and RS frame coefficients (`ScopedChunkKey`) to S3. |
| `chunk_reader.go` | `ChunkReader` — reads full objects (proofs, coefficients) or byte-range subsets (partial proofs, partial coefficients) via `DownloadPartialObject`. |

### `api/proxy/store/secondary/s3/` — proxy secondary store (minio-go)

| File | Role |
|---|---|
| `s3.go` | `Store` struct. Uses `minio-go` v7. Three credential modes: `static`, `iam`, `public`. Keys objects as `<path>/<hex(keccak(commitment))>`. Disables content-SHA256 on GCS endpoints (minio-go workaround). |
| `cli.go` | CLI flag definitions (prefix `s3.*`, env prefix `<PREFIX>_S3_*`). |
| `errors.go` | `ErrKeccakKeyNotFound`, `Keccak256KeyValueMismatchError`. |

### `common/aws/cli.go` — shared AWS config

Defines `ClientConfig` (region, access key, secret key, endpoint URL, parallelism settings) and `ClientFlags` / `ReadClientConfig` helpers consumed by every component that uses the AWS-backed S3 client.

---

## System Flows

### Blob dispersal (v2)

```
Client → DisperserAPIServer
   │  StoreBlob()
   ▼
BlobStore.StoreBlob()
   │  HeadObject (duplicate check)
   │  UploadObject → S3: "<3-char-prefix>/blob/<blobKeyHex>"
   ▼
DynamoDB metadata record

EncodingManager (Controller) pulls blob from DynamoDB queue
   │  GetBlob() → DownloadObject ← S3
   │  → Encoder gRPC: KZG proof + RS encoding
   ▼
ChunkWriter
   │  PutFrameProofs()      → UploadObject → S3: "<prefix>/proof/<blobKeyHex>"
   │  PutFrameCoefficients() → UploadObject → S3: "<prefix>/chunk/<blobKeyHex>"
   ▼
Controller/Dispatcher sends chunks to operator nodes
```

### Relay serving (v2)

```
Operator / client → Relay gRPC (GetBlob / GetChunks)
   │
   ├─ GetBlob()
   │    BlobStore.GetBlob() → DownloadObject ← S3: "<prefix>/blob/<blobKeyHex>"
   │
   └─ GetChunks()
        ChunkReader.GetBinaryChunkProofsRange()
             → DownloadPartialObject ← S3 (HTTP Range: bytes=N-M)
        ChunkReader.GetBinaryChunkCoefficientRange()
             → DownloadPartialObject ← S3 (HTTP Range: bytes=N-M)
```

### Proxy secondary store (OP-keccak / caching)

```
OP rollup sequencer → EigenDA Proxy PUT /put/<commitment>
   │
   ├─ EigenDA dispersal (primary)
   └─ secondary.HandleRedundantWrites()
         → s3.Store.Put(keccak(commitment), value)
              minio.PutObject → S3: "<path>/<hex(keccak(commitment))>"

OP rollup derivation → Proxy GET /get/<commitment>
   ├─ EigenDA read (primary)
   └─ on miss: secondary.MultiSourceRead()
         → s3.Store.Get(keccak(commitment))
              minio.GetObject ← S3
```

---

## External Dependencies

| Library | Version | Used For |
|---|---|---|
| `github.com/aws/aws-sdk-go-v2` | v1.26.1 | Core AWS SDK v2 infrastructure |
| `github.com/aws/aws-sdk-go-v2/service/s3` | v1.53.0 | S3 service client (`GetObject`, `PutObject`, `HeadObject`, `DeleteObject`, `ListObjectsV2`, `CreateBucket`) |
| `github.com/aws/aws-sdk-go-v2/feature/s3/manager` | v1.16.13 | `manager.Uploader` and `manager.Downloader` for multipart transfers |
| `github.com/aws/aws-sdk-go-v2/config` | v1.27.11 | `config.LoadDefaultConfig`, endpoint resolver, retry mode |
| `github.com/aws/aws-sdk-go-v2/credentials` | v1.17.11 | `credentials.NewStaticCredentialsProvider` for explicit key/secret |
| `github.com/minio/minio-go/v7` | v7.0.85 | S3-compatible client for the proxy secondary store (AWS, GCS, MinIO) |
| `github.com/oracle/oci-go-sdk/v65` | v65.78.0 | OCI Object Storage backend |

---

## API Surface

### AWS SDK v2 operations (disperser / relay path)

| Operation | Method | Auth | Purpose |
|---|---|---|---|
| `HeadObject` | HEAD | SigV4 | Check existence before upload (dedup); check chunk existence (`ProofExists`, `CoefficientsExists`) |
| `PutObject` (via manager.Uploader) | PUT | SigV4 | Upload blob bytes, chunk coefficients, KZG proofs |
| `GetObject` (via manager.Downloader) | GET | SigV4 | Download full blob or full chunk/proof object |
| `GetObject` with `Range` header (via manager.Downloader) | GET | SigV4 | Download a byte range of a chunk/proof object for partial serving |
| `DeleteObject` | DELETE | SigV4 | Object deletion (available on interface; used in cleanup paths) |
| `ListObjectsV2` | GET (list) | SigV4 | Enumerate objects by prefix (up to 1000 items) |
| `CreateBucket` | PUT | SigV4 | Bucket creation (test setup) |

**Transfer parameters** (AWS SDK path):
- Part size: 10 MiB per part
- Concurrency per transfer: 3 goroutines
- Worker pool for parallel blob fetches (v1): up to 64 workers
- Worker pool for all S3 I/O (aws client): `FragmentParallelismFactor * NumCPU` or `FragmentParallelismConstant` (default: 8× CPU)
- Retry mode: `aws.RetryModeStandard`
- Path-style addressing: `UsePathStyle = true` (required for LocalStack / MinIO compatibility)

### minio-go operations (proxy track)

| Operation | Auth | Purpose |
|---|---|---|
| `minio.PutObject` | static V4 / IAM / public | Store blob payload keyed by `keccak(commitment)` |
| `minio.GetObject` | static V4 / IAM / public | Retrieve blob payload by `keccak(commitment)` |

**Note**: GCS endpoints disable content-SHA256 chunked signing (`DisableContentSha256 = true`) to work around a known minio-go issue with GCS.

---

## Configuration

### Disperser / Relay / Encoder (AWS SDK path)

Env var prefix varies per component: `DISPERSER_ENCODER_`, `RELAY_`, `DISPERSER_APISERVER_`, `DISPERSER_CONTROLLER_`.

| Env Var (example for encoder) | Flag | Required | Default | Description |
|---|---|---|---|---|
| `DISPERSER_ENCODER_AWS_REGION` | `aws.region` | Yes | — | AWS region |
| `DISPERSER_ENCODER_AWS_ACCESS_KEY_ID` | `aws.access-key-id` | No | `""` | Static access key; if empty, default credential chain is used |
| `DISPERSER_ENCODER_AWS_SECRET_ACCESS_KEY` | `aws.secret-access-key` | No | `""` | Static secret key |
| `DISPERSER_ENCODER_AWS_ENDPOINT_URL` | `aws.endpoint-url` | No | `""` | Override endpoint (LocalStack, MinIO) |
| `DISPERSER_ENCODER_AWS_FRAGMENT_PARALLELISM_FACTOR` | `aws.fragment-parallelism-factor` | No | `8` | Worker pool = factor × NumCPU |
| `DISPERSER_ENCODER_AWS_FRAGMENT_PARALLELISM_CONSTANT` | `aws.fragment-parallelism-constant` | No | `0` | Absolute worker pool size (overrides factor if >0) |
| `DISPERSER_ENCODER_S3_BUCKET_NAME` | `disperser-encoder.s3-bucket-name` | No | — | Bucket for blobs AND chunks (single bucket used for both) |
| `DISPERSER_ENCODER_OBJECT_STORAGE_BACKEND` | `disperser-encoder.object-storage-backend` | No | `s3` | `s3` or `oci` |
| `DISPERSER_ENCODER_OCI_REGION` | `disperser-encoder.oci-region` | No | — | OCI region (OCI backend only) |
| `DISPERSER_ENCODER_OCI_COMPARTMENT_ID` | `disperser-encoder.oci-compartment-id` | No | — | OCI compartment ID |
| `DISPERSER_ENCODER_OCI_NAMESPACE` | `disperser-encoder.oci-namespace` | No | — | OCI namespace; auto-resolved if empty |
| `RELAY_BUCKET_NAME` | `relay.bucket-name` | Yes | — | Bucket for relay blob/chunk reads |
| `RELAY_OBJECT_STORAGE_BACKEND` | `relay.object-storage-backend` | No | `s3` | `s3` or `oci` |

### Proxy secondary store (minio-go path)

Env var prefix: `<PREFIX>_S3_*` (e.g., `EIGENDA_PROXY_S3_*`).

| Env Var | Flag | Description |
|---|---|---|
| `<PREFIX>_S3_ENDPOINT` | `s3.endpoint` | Endpoint hostname (no scheme for minio-go) |
| `<PREFIX>_S3_ENABLE_TLS` | `s3.enable-tls` | Enable TLS on the minio-go connection |
| `<PREFIX>_S3_CREDENTIAL_TYPE` | `s3.credential-type` | `static`, `iam`, or `public` |
| `<PREFIX>_S3_ACCESS_KEY_ID` | `s3.access-key-id` | Static access key (used when credential-type=static) |
| `<PREFIX>_S3_ACCESS_KEY_SECRET` | `s3.access-key-secret` | Static secret key |
| `<PREFIX>_S3_BUCKET` | `s3.bucket` | Bucket name |
| `<PREFIX>_S3_PATH` | `s3.path` | Optional key path prefix |

---

## Security Considerations

### Authentication

**AWS SDK path**: defaults to the AWS standard credential provider chain (environment variables, EC2 instance metadata, ECS task role, etc.). Explicit `AccessKey` + `SecretAccessKey` fields activate `credentials.NewStaticCredentialsProvider`, bypassing the chain. In production deployments using IAM roles (EC2/ECS/EKS), no static keys need to be set.

**OCI path**: uses OKE Workload Identity (`auth.OkeWorkloadIdentityConfigurationProvider`). No static credentials are involved.

**minio-go path**: three modes:
- `static` — `credentials.NewStaticV4` with key/secret from config.
- `iam` — `credentials.NewIAM("")` (EC2/ECS instance role).
- `public` — no credentials (nil). Only suitable for public buckets.

### Credential handling

- The `Config.MarshalJSON` in the proxy's S3 store masks `AccessKeySecret` with `"*****"` in log output.
- `SecretAccessKey` in `aws.ClientConfig` has a TODO comment noting it should become a `*secret.Secret` type — it is currently a plain string.
- The `#nosec G101` annotations on `AccessKeyIDFlagName` and `AccessKeySecretFlagName` suppress gosec false positives for these flag names.

### Data integrity

- The v2 `BlobStore.StoreBlob` does a `HeadObject` check before upload to avoid silent overwrites of existing blobs.
- The proxy secondary store verifies data on read: `Verify()` computes `keccak256(value)` and compares it to the stored key. A mismatch returns `Keccak256KeyValueMismatchError`.
- Secondary write retries are performed 5× with exponential backoff before failure is declared.

### Failure modes

- **AWS SDK**: A `StatusCode: 404` string check is used for `DownloadObject` not-found detection (in addition to `types.NoSuchKey` for `DownloadPartialObject`). This is a fragile string match; other callers rely on `errors.As(err, &types.NotFound{})`.
- **Singleton client**: `aws_s3_client.go` uses `sync.Once` to create a single `awsS3Client` per process. If `NewAwsS3Client` is called with different configurations in the same process, only the first call takes effect; subsequent calls silently return the already-created singleton.
- **OCI not tested with live credentials**: The OCI methods carry a comment explicitly noting 0% test coverage because they require live OCI credentials.
- **ListObjects capped at 1000**: Both AWS (`ListObjectsV2`) and OCI (`Limit: 1000`) implementations return at most 1000 items. There is no pagination.
- **`DeleteObject` bug**: The AWS `DeleteObject` method returns `err` in its final `return err` statement after already checking for error, but returns the same value twice — effectively harmless but incorrect (returns `nil` even if the DeleteObject call succeeded, since the only `err` set is from the SDK call itself).
- **Secondary writes decouple from primary**: By default, secondary S3 writes in the proxy are synchronous but optional — failure only causes a warning log unless `error-on-secondary-insert-failure` is set, which can block the rollup batch poster.

### Network and endpoint flexibility

- `UsePathStyle = true` is set on the AWS SDK client, which is required for MinIO, LocalStack, and other non-AWS endpoints where virtual-hosted-style addressing is not available.
- The custom endpoint resolver falls back to AWS default resolution when `endpointUrl` is empty, ensuring no configuration drift for standard AWS deployments.
- minio-go's GCS-specific `DisableContentSha256 = true` workaround shows awareness of multi-cloud compatibility requirements.
