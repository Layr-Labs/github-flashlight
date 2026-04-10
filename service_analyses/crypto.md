# crypto Analysis

**Analyzed by**: code-library-analyzer
**Timestamp**: 2026-04-10T00:00:00Z
**Package Type**: go-module
**Classification**: library
**Location**: crypto/

## Architecture

The `crypto` library is a focused cryptographic utility package for the EigenDA system, located at `crypto/ecc/bn254/`. It contains exactly two source files — `attestation.go` and `utils.go` — and provides all BLS (Boneh-Lynn-Shacham) signature primitives required by EigenDA's operator registration and data availability attestation protocols, as well as generic pairing-based verification utilities consumed by the KZG polynomial commitment subsystem.

The library is built around the **BN254 elliptic curve** (also known as alt-bn128). BN254 is a pairing-friendly curve with native support in the Ethereum EVM via precompiles (EIP-196 and EIP-197). This deliberate choice allows the Solidity smart contract layer to verify the same cryptographic operations performed off-chain in Go, a fundamental requirement of EigenDA's decentralized data availability protocol. Every on-chain operator identity and every aggregate signature is verifiable using the same BN254 arithmetic.

The design follows a **thin-wrapper pattern**: the library wraps the `github.com/consensys/gnark-crypto` library's low-level types (`bn254.G1Affine`, `bn254.G2Affine`, `fr.Element`, `fp.Element`) with domain-specific Go structs (`G1Point`, `G2Point`, `Signature`, `KeyPair`) that add semantic meaning and higher-level operations appropriate to the EigenDA context. There is no framework, no HTTP layer, no persistent storage, and no configuration system — just pure, stateless cryptographic operations exposed as a Go package.

The library's two files divide responsibilities cleanly: `attestation.go` handles identity and key lifecycle (key generation, message signing, and operator registration), while `utils.go` provides the lower-level mathematical building blocks (pairing verification, hash-to-curve mapping, generator point access, scalar multiplication, and random field element generation). Both files belong to Go package `bn254` under the import path `github.com/Layr-Labs/eigenda/crypto/ecc/bn254`.

An important architectural note: a near-identical copy of much of this library's logic exists at `core/bn254/attestation.go`. The `core` package re-implements the same high-level types (`G1Point`, `G2Point`, `KeyPair`, `Signature`) and delegates to `core/bn254` for the lower-level operations. The `crypto/ecc/bn254` package is the canonical implementation used by the KZG encoding subsystem (`encoding/v2/kzg/`), while `core` uses its own parallel types for operator attestation flows. This duplication is a known architectural quirk in the EigenDA codebase.

## Key Components

- **G1Point** (`crypto/ecc/bn254/attestation.go`): A wrapper around `*bn254.G1Affine` representing a point on the G1 group of the BN254 curve. Provides arithmetic operations (`Add`, `Sub`), cross-group verification (`VerifyEquivalence`), serialization (`Serialize`, `Deserialize`), deep copy (`Clone`), and hashing (`Hash`, `GetOperatorID`). The `GetOperatorID` method is particularly critical: it computes `keccak256(abi.encodePacked(pk.X, pk.Y))`, exactly matching the Solidity BN254 library's operator ID derivation and serving as the bridge between on-chain operator identity and off-chain key material.

- **G2Point** (`crypto/ecc/bn254/attestation.go`): A wrapper around `*bn254.G2Affine` representing a point on the G2 group (a degree-2 extension field over the BN254 base field). Provides `Add`, `Sub`, `Serialize`, `Deserialize`, and `Clone`. G2 points serve as public keys in the BLS scheme; the corresponding G1 scalar (private key) is used for signing, while G2 public keys are registered on-chain and used for aggregate verification.

- **Signature** (`crypto/ecc/bn254/attestation.go`): A named wrapper around `*G1Point` representing a BLS signature. Its `Verify(pubkey *G2Point, message [32]byte) bool` method delegates to `VerifySig`, which performs the bilinear pairing check `e(H(msg), pubkey) * e(-sig, G2Generator) == 1` to confirm the signature is valid.

- **KeyPair** (`crypto/ecc/bn254/attestation.go`): Holds `PrivKey *PrivateKey` (an `fr.Element`, a scalar in the BN254 scalar field) and `PubKey *G1Point`. Offers three constructor paths — `MakeKeyPair(sk)`, `MakeKeyPairFromString(sk string)`, and `GenRandomBlsKeys()` — and methods for signing (`SignMessage`, `SignHashedToCurveMessage`), public key retrieval (`GetPubKeyG1`, `GetPubKeyG2`), and operator registration (`MakePubkeyRegistrationData`).

- **PrivateKey** (`crypto/ecc/bn254/attestation.go`): A type alias for `fr.Element`, an element of the BN254 scalar field (the finite field of order equal to the curve group order). As a type alias (`type PrivateKey = fr.Element`) rather than a new type, it is directly interchangeable with `fr.Element` in function signatures, which simplifies interop with gnark-crypto APIs.

- **PairingsVerify** (`crypto/ecc/bn254/utils.go`): The primary pairing verification primitive exported by this library. Takes two G1/G2 point pairs and checks `e(a1, a2) == e(b1, b2)` by verifying `e(a1, a2) * e(-b1, b2) == 1`. This is the function called by the KZG encoding/verification subsystem for both frame proofs and length proofs. Returns `error` (not `bool`) so callers get descriptive failure messages.

- **VerifySig** (`crypto/ecc/bn254/utils.go`): Verifies a BLS signature using the optimized pairing equation `e(H(msg), pubkey) * e(-sig, G2Generator) == 1`. Operates directly on `*bn254.G1Affine` and `*bn254.G2Affine` rather than the wrapper types, making it usable from both this package and `core/bn254`.

- **MapToCurve** (`crypto/ecc/bn254/utils.go`): Implements hash-to-G1 using the "try-and-increment" method. Interprets the 32-byte input digest as an integer x-coordinate, then iterates incrementing x modulo the field prime until `x^3 + 3` is a quadratic residue (i.e., a perfect square modulo the prime), yielding a valid BN254 curve point. This matches the hash-to-curve behavior in EigenDA's Solidity contracts, ensuring on-chain/off-chain compatibility.

- **CheckG1AndG2DiscreteLogEquality** (`crypto/ecc/bn254/utils.go`): Verifies that a G1 point and a G2 point represent the same scalar (i.e., share the same discrete logarithm base their respective generators). Uses the pairing equation `e(P_G1, G2Gen) * e(-G1Gen, P_G2) == 1`. Used by `G1Point.VerifyEquivalence` to confirm that a public key's G1 and G2 representations are consistent.

- **GetG1Generator / GetG2Generator** (`crypto/ecc/bn254/utils.go`): Returns the canonical BN254 generator points. G1 generator is (x=1, y=2); G2 generator uses the standard hardcoded coordinates from the BN254 specification. These are used as base points for all scalar multiplications producing public keys and signatures.

- **RandomFrs** (`crypto/ecc/bn254/utils.go`): Generates a vector of `n` deterministic-from-single-seed random field elements as a geometric sequence: `[r, r^2, r^3, ..., r^n]` where `r` is drawn from `crypto/rand`. This specific structure (powers of a single random value) allows batch KZG verification to construct a random linear combination using a single source of randomness, reducing the cost of randomness generation during high-throughput verification.

- **MakePubkeyRegistrationData** (`crypto/ecc/bn254/utils.go`): Produces the proof-of-possession required for operator public key registration, defending against rogue-key attacks. Computes an EIP-712-style hash `keccak256(keccak256("BN254PubkeyRegistration(address operator)") || operatorAddress)`, maps the hash to a G1 curve point, and multiplies by the private key scalar. The resulting signature can be verified on-chain against the registered G2 public key to confirm the operator controls the corresponding private key.

## Data Flows

### 1. BLS Key Generation

An EigenDA operator generates a cryptographic identity to participate in the network.

```mermaid
sequenceDiagram
    participant Caller
    participant GenRandomBlsKeys
    participant rand.Reader
    participant MakeKeyPair
    participant MulByGeneratorG1

    Caller->>GenRandomBlsKeys: GenRandomBlsKeys()
    GenRandomBlsKeys->>rand.Reader: rand.Int(rand.Reader, fr.Modulus())
    rand.Reader--->>GenRandomBlsKeys: random big.Int n in [0, curve_order)
    Note over GenRandomBlsKeys: sk = new(fr.Element).SetBigInt(n)
    GenRandomBlsKeys->>MakeKeyPair: MakeKeyPair(sk)
    MakeKeyPair->>MulByGeneratorG1: MulByGeneratorG1(sk)
    MulByGeneratorG1--->>MakeKeyPair: *bn254.G1Affine (pubkey = sk * G1Gen)
    MakeKeyPair--->>GenRandomBlsKeys: &KeyPair{PrivKey: sk, PubKey: G1Point{pk}}
    GenRandomBlsKeys--->>Caller: *KeyPair
```

**Detailed Steps**:

1. **Random scalar generation** (`GenRandomBlsKeys`, `attestation.go:167`): `rand.Int(rand.Reader, fr.Modulus())` draws a uniform random integer in `[0, curve_order)` from the OS CSPRNG. The field modulus bounds the sample to valid scalar values.
2. **Private key construction** (`attestation.go:173`): `new(PrivateKey).SetBigInt(n)` converts the big.Int to an `fr.Element`.
3. **Public key derivation** (`MakeKeyPair`, `attestation.go:148-151`): Calls `MulByGeneratorG1(sk)` which performs `sk * G1Generator` via scalar multiplication using gnark-crypto's optimized scalar multiplication.
4. **Output**: `*KeyPair` with `PrivKey` (scalar) and `PubKey` (G1 point) ready for signing and registration.

**Error Paths**:
- `rand.Int` failure → `GenRandomBlsKeys` returns `(nil, error)`

---

### 2. BLS Message Signing

An operator signs a 32-byte batch header hash for aggregated attestation.

```mermaid
sequenceDiagram
    participant Caller
    participant KeyPair.SignMessage
    participant MapToCurve
    participant bn254.ScalarMultiplication

    Caller->>KeyPair.SignMessage: k.SignMessage(message [32]byte)
    KeyPair.SignMessage->>MapToCurve: MapToCurve(message)
    Note over MapToCurve: try-and-increment loop<br/>x = int(message); while y^2!=x^3+3: x++
    MapToCurve--->>KeyPair.SignMessage: H *bn254.G1Affine (hash point)
    KeyPair.SignMessage->>bn254.ScalarMultiplication: ScalarMultiplication(H, privKey)
    bn254.ScalarMultiplication--->>KeyPair.SignMessage: sig *bn254.G1Affine
    KeyPair.SignMessage--->>Caller: &Signature{&G1Point{sig}}
```

**Detailed Steps**:

1. **Hash-to-curve** (`MapToCurve`, `utils.go:54-78`): Interprets the 32-byte digest as a `big.Int` x-coordinate. Iterates computing `y = sqrt(x^3 + 3) mod p`; if no square root exists, increments x. Returns the first valid `G1Affine` point found.
2. **Scalar multiplication** (`attestation.go:179`): `new(bn254.G1Affine).ScalarMultiplication(H, privKey.BigInt(...))` computes `sig = privKey * H(message)`.
3. **Output**: `*Signature` embedding a `*G1Point` representing the BLS signature.

---

### 3. BLS Signature Verification

Verifying that a signature is valid for a given message and public key, used during consensus aggregation.

```mermaid
sequenceDiagram
    participant Caller
    participant Signature.Verify
    participant VerifySig
    participant MapToCurve
    participant bn254.PairingCheck

    Caller->>Signature.Verify: s.Verify(pubkey *G2Point, message [32]byte)
    Signature.Verify->>VerifySig: VerifySig(s.G1Affine, pubkey.G2Affine, message)
    VerifySig->>MapToCurve: MapToCurve(msgBytes)
    MapToCurve--->>VerifySig: msgPoint *bn254.G1Affine
    Note over VerifySig: negSig = Neg(sig)
    VerifySig->>bn254.PairingCheck: PairingCheck([H(msg), -sig], [pubkey, G2Gen])
    bn254.PairingCheck--->>VerifySig: (ok bool, err error)
    VerifySig--->>Signature.Verify: bool
    Signature.Verify--->>Caller: bool
```

**Detailed Steps**:

1. **Hash-to-curve** (`VerifySig`, `utils.go:38`): `MapToCurve(msgBytes)` reproduces the G1 message point deterministically.
2. **Negate signature** (`utils.go:40-41`): `negSig.Neg(sig)` computes `-sig` in G1.
3. **Bilinear pairing** (`utils.go:43-49`): `PairingCheck([H(msg), -sig], [pubkey, G2Gen])` verifies `e(H(msg), pubkey) * e(-sig, G2Gen) == 1`, which holds if and only if `sig = privKey * H(msg)` and `pubkey = privKey * G2Gen`.
4. **Output**: `true` if valid, `false` on failure or error.

---

### 4. KZG Polynomial Commitment Batch Verification

The KZG verifier uses `PairingsVerify` and `RandomFrs` to verify multiple polynomial evaluation proofs in a single pairing call.

```mermaid
sequenceDiagram
    participant universalVerify
    participant eigenbn254.RandomFrs
    participant lhsG1.MultiExp
    participant genRhsG1
    participant eigenbn254.PairingsVerify
    participant bn254.PairingCheck

    universalVerify->>eigenbn254.RandomFrs: RandomFrs(n)
    eigenbn254.RandomFrs--->>universalVerify: []fr.Element [r, r^2, ..., r^n]
    universalVerify->>lhsG1.MultiExp: MultiExp(proofs, randomsFr)
    lhsG1.MultiExp--->>universalVerify: lhsG1 *bn254.G1Affine (aggregated proof)
    universalVerify->>genRhsG1: genRhsG1(samples, randomsFr, ...)
    genRhsG1--->>universalVerify: rhsG1 *bn254.G1Affine
    universalVerify->>eigenbn254.PairingsVerify: PairingsVerify(lhsG1, lhsG2, rhsG1, rhsG2)
    eigenbn254.PairingsVerify->>bn254.PairingCheck: PairingCheck([lhsG1, -rhsG1], [lhsG2, rhsG2])
    bn254.PairingCheck--->>eigenbn254.PairingsVerify: (ok, err)
    eigenbn254.PairingsVerify--->>universalVerify: nil or error
```

**Detailed Steps**:

1. **Random coefficients** (`RandomFrs`, `utils.go:133`): `RandomFrs(n)` generates the geometric sequence `[r, r^2, ..., r^n]` as a random linear combination vector.
2. **Aggregate LHS proof** (`verifier.go`): `MultiExp(proofs, randomsFr)` computes `sum(r^i * proof_i)` as a single G1 point.
3. **Aggregate RHS** (`genRhsG1`): Computes the aggregated commitment adjusted by evaluation points.
4. **Pairing equality check** (`PairingsVerify`, `utils.go:16`): Verifies `e(lhsG1, lhsG2) == e(rhsG1, rhsG2)` confirming all frames satisfy the KZG equation simultaneously.

---

### 5. Operator Registration Proof-of-Possession

An operator registers their BLS public key on-chain while proving knowledge of the corresponding private key, preventing rogue-key attacks.

```mermaid
sequenceDiagram
    participant Operator
    participant KeyPair.MakePubkeyRegistrationData
    participant MakePubkeyRegistrationData_fn
    participant crypto.Keccak256
    participant MapToCurve
    participant ScalarMultiplication

    Operator->>KeyPair.MakePubkeyRegistrationData: MakePubkeyRegistrationData(operatorAddress)
    KeyPair.MakePubkeyRegistrationData->>MakePubkeyRegistrationData_fn: MakePubkeyRegistrationData(privKey, addr)
    MakePubkeyRegistrationData_fn->>crypto.Keccak256: Keccak256("BN254PubkeyRegistration(address operator)")
    crypto.Keccak256--->>MakePubkeyRegistrationData_fn: domain hash bytes
    Note over MakePubkeyRegistrationData_fn: append operatorAddress bytes
    MakePubkeyRegistrationData_fn->>crypto.Keccak256: Keccak256(domainHash || operatorAddress)
    crypto.Keccak256--->>MakePubkeyRegistrationData_fn: msgHash [32]byte
    MakePubkeyRegistrationData_fn->>MapToCurve: MapToCurve(msgHash32)
    MapToCurve--->>MakePubkeyRegistrationData_fn: hashToSign *bn254.G1Affine
    MakePubkeyRegistrationData_fn->>ScalarMultiplication: ScalarMultiplication(hashToSign, privKey)
    ScalarMultiplication--->>MakePubkeyRegistrationData_fn: proof *bn254.G1Affine
    MakePubkeyRegistrationData_fn--->>Operator: &G1Point{proof}
```

**Detailed Steps**:

1. **Domain separation** (`utils.go:119`): Hashes the EIP-712-style type string `"BN254PubkeyRegistration(address operator)"` with Keccak256.
2. **Message construction** (`utils.go:120`): Concatenates the domain hash with the operator's 20-byte Ethereum address.
3. **Message hash** (`utils.go:122`): Second Keccak256 over the concatenation produces a 32-byte message.
4. **Hash-to-curve** (`utils.go:128`): `MapToCurve(msgHash32)` maps the message hash to a G1 point.
5. **Sign** (`utils.go:130`): `privKey * H(msg)` produces the proof-of-possession G1 point.
6. **Output**: `*G1Point` submitted on-chain alongside the G2 public key; the smart contract verifies `e(proof, G2Gen) == e(H(msg), pubkey_G2)`.

## Dependencies

### External Libraries

- **github.com/consensys/gnark-crypto** (v0.18.0) [crypto]: The foundational ZK cryptography library providing all BN254 elliptic curve arithmetic. Supplies `bn254.G1Affine`, `bn254.G2Affine`, `bn254.PairingCheck`, `fp.Element` (base field arithmetic), `fr.Element` (scalar field arithmetic), and group operations including scalar multiplication, point addition/subtraction/negation, and multi-exponentiation. Every cryptographic operation in the `crypto` library ultimately calls into gnark-crypto's highly optimized, assembly-accelerated field arithmetic.
  Imported in: `crypto/ecc/bn254/attestation.go`, `crypto/ecc/bn254/utils.go`.

- **github.com/ethereum/go-ethereum** (v1.15.3, replaced by `github.com/ethereum-optimism/op-geth v1.101511.1`) [blockchain]: The Ethereum client library. Used for three specific utilities: `github.com/ethereum/go-ethereum/crypto` provides `Keccak256Hash` (hashing G1 point coordinates to produce `G1Point.Hash()`) and `Keccak256` (building EIP-712-style operator registration message hashes); `github.com/ethereum/go-ethereum/common` provides `common.Address` for operator Ethereum addresses; `github.com/ethereum/go-ethereum/common/math` provides `math.U256Bytes` which encodes field elements as 32-byte big-endian integers matching EVM ABI encoding used in `GetOperatorID`.
  Imported in: `crypto/ecc/bn254/attestation.go`, `crypto/ecc/bn254/utils.go`.

### Internal Libraries

This library has no internal library dependencies within the EigenDA codebase. It is a leaf-level package in the dependency graph, depending only on external third-party libraries and the Go standard library (`crypto/rand`, `math/big`, `errors`, `fmt`).

## API Surface

The package `github.com/Layr-Labs/eigenda/crypto/ecc/bn254` exports the following public API consumed by the KZG encoding subsystem and relay tests.

### Exported Types

```go
// G1Point wraps a BN254 G1 group element with domain-specific operations
type G1Point struct {
    *bn254.G1Affine
}

// G2Point wraps a BN254 G2 group element
type G2Point struct {
    *bn254.G2Affine
}

// Signature is a BLS signature residing in the G1 group
type Signature struct {
    *G1Point
}

// KeyPair holds a BLS private key and its corresponding G1 public key
type KeyPair struct {
    PrivKey *PrivateKey
    PubKey  *G1Point
}

// PrivateKey is a scalar in the BN254 scalar field (type alias for fr.Element)
type PrivateKey = fr.Element
```

### G1Point Methods

```go
func NewG1Point(x, y *big.Int) *G1Point
func (p *G1Point) Add(p2 *G1Point)
func (p *G1Point) Sub(p2 *G1Point)
func (p *G1Point) VerifyEquivalence(p2 *G2Point) (bool, error)
func (p *G1Point) Serialize() []byte
func (p *G1Point) Deserialize(data []byte) (*G1Point, error)
func (p *G1Point) Clone() *G1Point
func (p *G1Point) Hash() [32]byte
func (p *G1Point) GetOperatorID() [32]byte
```

### G2Point Methods

```go
func (p *G2Point) Add(p2 *G2Point)
func (p *G2Point) Sub(p2 *G2Point)
func (p *G2Point) Serialize() []byte
func (p *G2Point) Deserialize(data []byte) (*G2Point, error)
func (p *G2Point) Clone() *G2Point
```

### Signature Methods

```go
func (s *Signature) Verify(pubkey *G2Point, message [32]byte) bool
```

### KeyPair Constructors and Methods

```go
func MakeKeyPair(sk *PrivateKey) *KeyPair
func MakeKeyPairFromString(sk string) (*KeyPair, error)
func GenRandomBlsKeys() (*KeyPair, error)
func (k *KeyPair) SignMessage(message [32]byte) *Signature
func (k *KeyPair) SignHashedToCurveMessage(g1HashedMsg *G1Point) *Signature
func (k *KeyPair) GetPubKeyG1() *G1Point
func (k *KeyPair) GetPubKeyG2() *G2Point
func (k *KeyPair) MakePubkeyRegistrationData(operatorAddress common.Address) *G1Point
```

### Cryptographic Utility Functions

```go
// PairingsVerify checks e(a1,a2) == e(b1,b2) using bilinear pairing
func PairingsVerify(a1 *bn254.G1Affine, a2 *bn254.G2Affine, b1 *bn254.G1Affine, b2 *bn254.G2Affine) error

// VerifySig verifies a BLS signature over a raw 32-byte message
func VerifySig(sig *bn254.G1Affine, pubkey *bn254.G2Affine, msgBytes [32]byte) (bool, error)

// MapToCurve hashes a 32-byte digest to a BN254 G1 point via try-and-increment
func MapToCurve(digest [32]byte) *bn254.G1Affine

// CheckG1AndG2DiscreteLogEquality verifies G1 and G2 points share the same discrete log
func CheckG1AndG2DiscreteLogEquality(pointG1 *bn254.G1Affine, pointG2 *bn254.G2Affine) (bool, error)

// Generator accessors
func GetG1Generator() *bn254.G1Affine
func GetG2Generator() *bn254.G2Affine
func MulByGeneratorG1(a *fr.Element) *bn254.G1Affine
func MulByGeneratorG2(a *fr.Element) *bn254.G2Affine

// MakePubkeyRegistrationData creates a proof-of-possession for operator registration
func MakePubkeyRegistrationData(privKey *fr.Element, operatorAddress common.Address) *bn254.G1Affine

// RandomFrs generates [r, r^2, ..., r^n] for batch verification randomness
func RandomFrs(n int) ([]fr.Element, error)
```

## Code Examples

### Example 1: BLS Key Generation and Signing

```go
// crypto/ecc/bn254/attestation.go lines 161-181
func GenRandomBlsKeys() (*KeyPair, error) {
    max := new(big.Int)
    max.SetString(fr.Modulus().String(), 10)
    n, err := rand.Int(rand.Reader, max)
    if err != nil {
        return nil, err
    }
    sk := new(PrivateKey).SetBigInt(n)
    return MakeKeyPair(sk), nil
}

func (k *KeyPair) SignMessage(message [32]byte) *Signature {
    H := MapToCurve(message)
    sig := new(bn254.G1Affine).ScalarMultiplication(H, k.PrivKey.BigInt(new(big.Int)))
    return &Signature{&G1Point{sig}}
}
```

### Example 2: Hash-to-Curve (Try-and-Increment)

```go
// crypto/ecc/bn254/utils.go lines 54-78
func MapToCurve(digest [32]byte) *bn254.G1Affine {
    one := new(big.Int).SetUint64(1)
    three := new(big.Int).SetUint64(3)
    x := new(big.Int)
    x.SetBytes(digest[:])
    for {
        // y^2 = x^3 + 3 (BN254 curve equation: b=3)
        xP3 := new(big.Int).Exp(x, big.NewInt(3), fp.Modulus())
        y := new(big.Int).Add(xP3, three)
        y.Mod(y, fp.Modulus())
        if y.ModSqrt(y, fp.Modulus()) == nil {
            x.Add(x, one).Mod(x, fp.Modulus())
        } else {
            var fpX, fpY fp.Element
            fpX.SetBigInt(x)
            fpY.SetBigInt(y)
            return &bn254.G1Affine{X: fpX, Y: fpY}
        }
    }
}
```

### Example 3: Bilinear Pairing Verification

```go
// crypto/ecc/bn254/utils.go lines 16-32
func PairingsVerify(a1 *bn254.G1Affine, a2 *bn254.G2Affine, b1 *bn254.G1Affine, b2 *bn254.G2Affine) error {
    var negB1 bn254.G1Affine
    negB1.Neg(b1)
    P := [2]bn254.G1Affine{*a1, negB1}
    Q := [2]bn254.G2Affine{*a2, *b2}
    ok, err := bn254.PairingCheck(P[:], Q[:])
    if err != nil {
        return fmt.Errorf("PairingCheck: %w", err)
    }
    if !ok {
        return errors.New("PairingCheck pairing not ok.")
    }
    return nil
}
```

### Example 4: Operator ID Derivation (Solidity-Compatible)

```go
// crypto/ecc/bn254/attestation.go lines 135-139
func (p *G1Point) GetOperatorID() [32]byte {
    x := p.X.BigInt(new(big.Int))
    y := p.Y.BigInt(new(big.Int))
    // Matches keccak256(abi.encodePacked(pk.X, pk.Y)) in BN254.sol
    return crypto.Keccak256Hash(append(math.U256Bytes(x), math.U256Bytes(y)...))
}
```

### Example 5: Random Field Element Vector for Batch Verification

```go
// crypto/ecc/bn254/utils.go lines 133-152
func RandomFrs(n int) ([]fr.Element, error) {
    if n <= 0 {
        return nil, errors.New("the length of vector must be positive")
    }
    r, err := randomFr()
    if err != nil {
        return nil, err
    }
    randomsFr := make([]fr.Element, n)
    randomsFr[0].Set(&r)
    // Geometric sequence: [r, r^2, r^3, ..., r^n]
    for j := 0; j < n-1; j++ {
        randomsFr[j+1].Mul(&randomsFr[j], &r)
    }
    return randomsFr, nil
}
```

### Example 6: KZG Frame Pairing Verification (Consumer Usage)

```go
// encoding/v2/kzg/verifier/parametrized_verifier.go lines 85-88
// PairingsVerify used to verify KZG evaluation proof via pairing equation:
// e([commitment - interpolation_polynomial(s)], [1]) = e([proof], [s^n - x^n])
err = eigenbn254.PairingsVerify(&commitMinusInterpolation, &kzg.GenG2, &frame.Proof, &xnMinusYn)
if err != nil {
    return fmt.Errorf("verify pairing: %w", err)
}
```

## Files Analyzed

- `crypto/ecc/bn254/attestation.go` (203 lines) - BLS key management, signing, and operator registration data
- `crypto/ecc/bn254/utils.go` (164 lines) - Pairing verification, hash-to-curve, generator operations, random field elements
- `core/bn254/attestation.go` (110 lines) - Near-duplicate used by the `core` package (reference for comparison)
- `encoding/v2/kzg/verifier/verifier.go` (357 lines) - Consumer of `PairingsVerify` and `RandomFrs` for KZG batch verification
- `encoding/v2/kzg/verifier/parametrized_verifier.go` (90 lines) - KZG single frame verifier using `PairingsVerify`
- `encoding/v2/kzg/committer/verify_length_proof.go` (122 lines) - Length proof and commit equivalence verifier
- `relay/chunk_provider_test.go` (partial) - Test consumer using `crypto/ecc/bn254` types
- `encoding/serialization_test.go` (partial) - Test consumer using `crypto/ecc/bn254` types
- `go.mod` - Dependency versions

## Analysis Data

```json
{
  "summary": "The crypto library provides BN254 elliptic curve cryptographic primitives for EigenDA's operator identity and data availability attestation protocols. It wraps the gnark-crypto library with domain-specific types (G1Point, G2Point, Signature, KeyPair) for BLS signing and verification, and exposes low-level utilities (PairingsVerify, MapToCurve, RandomFrs) consumed by the KZG polynomial commitment encoding subsystem. All operations target EVM compatibility, matching the behavior of EigenDA's Solidity contracts on the alt-bn128 curve.",
  "architecture_pattern": "thin-wrapper library",
  "key_modules": [
    {
      "name": "attestation.go",
      "path": "crypto/ecc/bn254/attestation.go",
      "description": "BLS key lifecycle and signing: G1Point, G2Point, Signature, KeyPair types with constructors, signing methods, and operator ID/registration data generation"
    },
    {
      "name": "utils.go",
      "path": "crypto/ecc/bn254/utils.go",
      "description": "Low-level BN254 utilities: PairingsVerify, VerifySig, MapToCurve, CheckG1AndG2DiscreteLogEquality, generator accessors, MulByGenerator*, MakePubkeyRegistrationData, RandomFrs"
    }
  ],
  "api_endpoints": [],
  "data_flows": [
    "BLS key generation: rand.Reader -> fr.Element scalar -> G1 scalar mult -> KeyPair",
    "BLS signing: message [32]byte -> MapToCurve -> G1 point -> scalar mult by privKey -> Signature",
    "BLS verification: (sig G1, pubkey G2, message) -> MapToCurve + Neg + PairingCheck -> bool",
    "KZG batch verification: n proofs -> RandomFrs geometric sequence -> MultiExp aggregation -> PairingsVerify",
    "Operator registration: (privKey, address) -> Keccak256 domain hash -> MapToCurve -> scalar mult -> proof G1 point"
  ],
  "tech_stack": ["go", "gnark-crypto", "go-ethereum"],
  "external_integrations": [],
  "component_interactions": [
    {
      "target": "encoding/v2/kzg/verifier",
      "type": "library_usage",
      "description": "Imports eigenbn254.PairingsVerify for KZG frame proof verification and eigenbn254.RandomFrs for batch verification randomness"
    },
    {
      "target": "encoding/v2/kzg/committer",
      "type": "library_usage",
      "description": "Imports eigenbn254.PairingsVerify for length proof and commit equivalence batch verification"
    },
    {
      "target": "relay (tests)",
      "type": "library_usage",
      "description": "Imports crypto/ecc/bn254 types in chunk provider tests"
    },
    {
      "target": "encoding (tests)",
      "type": "library_usage",
      "description": "Imports crypto/ecc/bn254 types in serialization tests"
    }
  ]
}
```

## Citations

```json
[
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 1,
    "end_line": 13,
    "claim": "The library is in Go package 'bn254' and imports gnark-crypto and go-ethereum as its only external dependencies",
    "section": "Architecture",
    "snippet": "package bn254\n\nimport (\n\t\"crypto/rand\"\n\t\"math/big\"\n\n\t\"github.com/consensys/gnark-crypto/ecc/bn254\"\n\t\"github.com/consensys/gnark-crypto/ecc/bn254/fp\"\n\t\"github.com/consensys/gnark-crypto/ecc/bn254/fr\"\n\t\"github.com/ethereum/go-ethereum/common\"\n\t\"github.com/ethereum/go-ethereum/common/math\"\n\t\"github.com/ethereum/go-ethereum/crypto\"\n)"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 15,
    "end_line": 17,
    "claim": "G1Point wraps *bn254.G1Affine as a thin domain-specific type",
    "section": "Key Components",
    "snippet": "type G1Point struct {\n\t*bn254.G1Affine\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 44,
    "end_line": 47,
    "claim": "G1Point.VerifyEquivalence delegates to CheckG1AndG2DiscreteLogEquality to verify a point has the same discrete log in both groups",
    "section": "Key Components",
    "snippet": "func (p *G1Point) VerifyEquivalence(p2 *G2Point) (bool, error) {\n\treturn CheckG1AndG2DiscreteLogEquality(p.G1Affine, p2.G2Affine)\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 132,
    "end_line": 139,
    "claim": "GetOperatorID matches Solidity's keccak256(abi.encodePacked(pk.X, pk.Y)) using math.U256Bytes for EVM ABI compatibility",
    "section": "Key Components",
    "snippet": "func (p *G1Point) GetOperatorID() [32]byte {\n\tx := p.X.BigInt(new(big.Int))\n\ty := p.Y.BigInt(new(big.Int))\n\treturn crypto.Keccak256Hash(append(math.U256Bytes(x), math.U256Bytes(y)...))\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 119,
    "end_line": 130,
    "claim": "Signature wraps G1Point and its Verify method delegates to VerifySig for bilinear pairing-based signature verification",
    "section": "Key Components",
    "snippet": "type Signature struct {\n\t*G1Point\n}\n\nfunc (s *Signature) Verify(pubkey *G2Point, message [32]byte) bool {\n\tok, err := VerifySig(s.G1Affine, pubkey.G2Affine, message)\n\tif err != nil {\n\t\treturn false\n\t}\n\treturn ok\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 141,
    "end_line": 141,
    "claim": "PrivateKey is a type alias (not a new type) for fr.Element, making it directly interchangeable with gnark-crypto's scalar field type",
    "section": "Key Components",
    "snippet": "type PrivateKey = fr.Element"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 161,
    "end_line": 175,
    "claim": "GenRandomBlsKeys samples a uniform random scalar in [0, curve_order) using the OS CSPRNG via crypto/rand",
    "section": "Data Flows",
    "snippet": "func GenRandomBlsKeys() (*KeyPair, error) {\n\tmax := new(big.Int)\n\tmax.SetString(fr.Modulus().String(), 10)\n\tn, err := rand.Int(rand.Reader, max)\n\tif err != nil {\n\t\treturn nil, err\n\t}\n\tsk := new(PrivateKey).SetBigInt(n)\n\treturn MakeKeyPair(sk), nil\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 148,
    "end_line": 151,
    "claim": "MakeKeyPair derives the G1 public key by scalar multiplying the G1 generator by the private key scalar",
    "section": "Data Flows",
    "snippet": "func MakeKeyPair(sk *PrivateKey) *KeyPair {\n\tpk := MulByGeneratorG1(sk)\n\treturn &KeyPair{sk, &G1Point{pk}}\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 177,
    "end_line": 181,
    "claim": "SignMessage hashes the message to a G1 curve point then performs scalar multiplication by the private key to produce the BLS signature",
    "section": "Data Flows",
    "snippet": "func (k *KeyPair) SignMessage(message [32]byte) *Signature {\n\tH := MapToCurve(message)\n\tsig := new(bn254.G1Affine).ScalarMultiplication(H, k.PrivKey.BigInt(new(big.Int)))\n\treturn &Signature{&G1Point{sig}}\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 54,
    "end_line": 78,
    "claim": "MapToCurve implements hash-to-G1 via try-and-increment: interprets digest as x, iterates incrementing x until y^2 = x^3 + 3 has a solution mod the field prime",
    "section": "Key Components",
    "snippet": "func MapToCurve(digest [32]byte) *bn254.G1Affine {\n\tone := new(big.Int).SetUint64(1)\n\tthree := new(big.Int).SetUint64(3)\n\tx := new(big.Int)\n\tx.SetBytes(digest[:])\n\tfor {\n\t\txP3 := new(big.Int).Exp(x, big.NewInt(3), fp.Modulus())\n\t\ty := new(big.Int).Add(xP3, three)\n\t\ty.Mod(y, fp.Modulus())\n\t\tif y.ModSqrt(y, fp.Modulus()) == nil {\n\t\t\tx.Add(x, one).Mod(x, fp.Modulus())\n\t\t} else { ... }\n\t}\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 16,
    "end_line": 32,
    "claim": "PairingsVerify checks e(a1,a2)==e(b1,b2) by negating b1 and calling PairingCheck([a1,-b1],[a2,b2])==1",
    "section": "Key Components",
    "snippet": "func PairingsVerify(a1 *bn254.G1Affine, a2 *bn254.G2Affine, b1 *bn254.G1Affine, b2 *bn254.G2Affine) error {\n\tvar negB1 bn254.G1Affine\n\tnegB1.Neg(b1)\n\tP := [2]bn254.G1Affine{*a1, negB1}\n\tQ := [2]bn254.G2Affine{*a2, *b2}\n\tok, err := bn254.PairingCheck(P[:], Q[:])\n\t...\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 34,
    "end_line": 51,
    "claim": "VerifySig verifies a BLS signature via e(H(msg), pubkey) * e(-sig, G2Gen) == 1",
    "section": "Key Components",
    "snippet": "func VerifySig(sig *bn254.G1Affine, pubkey *bn254.G2Affine, msgBytes [32]byte) (bool, error) {\n\tg2Gen := GetG2Generator()\n\tmsgPoint := MapToCurve(msgBytes)\n\tvar negSig bn254.G1Affine\n\tnegSig.Neg((*bn254.G1Affine)(sig))\n\tP := [2]bn254.G1Affine{*msgPoint, negSig}\n\tQ := [2]bn254.G2Affine{*pubkey, *g2Gen}\n\tok, err := bn254.PairingCheck(P[:], Q[:])\n\t...\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 80,
    "end_line": 83,
    "claim": "CheckG1AndG2DiscreteLogEquality uses pairing equation e(P_G1, G2Gen) * e(-G1Gen, P_G2) == 1 to verify shared discrete log",
    "section": "Key Components",
    "snippet": "func CheckG1AndG2DiscreteLogEquality(pointG1 *bn254.G1Affine, pointG2 *bn254.G2Affine) (bool, error) {\n\tnegGenG1 := new(bn254.G1Affine).Neg(GetG1Generator())\n\treturn bn254.PairingCheck([]bn254.G1Affine{*pointG1, *negGenG1}, []bn254.G2Affine{*GetG2Generator(), *pointG2})\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 85,
    "end_line": 95,
    "claim": "G1 generator is the canonical BN254 G1 generator point (1, 2)",
    "section": "Key Components",
    "snippet": "func GetG1Generator() *bn254.G1Affine {\n\tg1Gen := new(bn254.G1Affine)\n\t_, err := g1Gen.X.SetString(\"1\")\n\t...\n\t_, err = g1Gen.Y.SetString(\"2\")\n\t...\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 98,
    "end_line": 105,
    "claim": "G2 generator uses hardcoded standard BN254 G2 generator coordinates",
    "section": "Key Components",
    "snippet": "func GetG2Generator() *bn254.G2Affine {\n\tg2Gen := new(bn254.G2Affine)\n\tg2Gen.X.SetString(\"10857046999023057135944570762232829481370756359578518086990519993285655852781\",\n\t\t\"11559732032986387107991004021392285783925812861821192530917403151452391805634\")\n\t...\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 107,
    "end_line": 115,
    "claim": "MulByGeneratorG1/G2 perform scalar multiplication against the respective generator points to derive public keys",
    "section": "Key Components",
    "snippet": "func MulByGeneratorG1(a *fr.Element) *bn254.G1Affine {\n\tg1Gen := GetG1Generator()\n\treturn new(bn254.G1Affine).ScalarMultiplication(g1Gen, a.BigInt(new(big.Int)))\n}\n\nfunc MulByGeneratorG2(a *fr.Element) *bn254.G2Affine {\n\tg2Gen := GetG2Generator()\n\treturn new(bn254.G2Affine).ScalarMultiplication(g2Gen, a.BigInt(new(big.Int)))\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 117,
    "end_line": 131,
    "claim": "MakePubkeyRegistrationData creates an EIP-712-style proof-of-possession preventing rogue-key attacks: sign H(keccak256(typestring) || operatorAddress)",
    "section": "Key Components",
    "snippet": "func MakePubkeyRegistrationData(privKey *fr.Element, operatorAddress common.Address) *bn254.G1Affine {\n\ttoHash := make([]byte, 0)\n\ttoHash = append(toHash, crypto.Keccak256([]byte(\"BN254PubkeyRegistration(address operator)\"))...)\n\ttoHash = append(toHash, operatorAddress.Bytes()...)\n\tmsgHash := crypto.Keccak256(toHash)\n\t...\n\treturn new(bn254.G1Affine).ScalarMultiplication(hashToSign, privKey.BigInt(new(big.Int)))\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/utils.go",
    "start_line": 133,
    "end_line": 152,
    "claim": "RandomFrs generates a geometric sequence [r, r^2, ..., r^n] from a single cryptographically random seed for use in batch verification",
    "section": "Key Components",
    "snippet": "func RandomFrs(n int) ([]fr.Element, error) {\n\t...\n\trandomsFr[0].Set(&r)\n\tfor j := 0; j < n-1; j++ {\n\t\trandomsFr[j+1].Mul(&randomsFr[j], &r)\n\t}\n\treturn randomsFr, nil\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 183,
    "end_line": 186,
    "claim": "SignHashedToCurveMessage signs a message that has already been hashed to a G1 point, supporting the case where hash-to-curve was done externally",
    "section": "API Surface",
    "snippet": "func (k *KeyPair) SignHashedToCurveMessage(g1HashedMsg *G1Point) *Signature {\n\tsig := new(bn254.G1Affine).ScalarMultiplication(g1HashedMsg.G1Affine, k.PrivKey.BigInt(new(big.Int)))\n\treturn &Signature{&G1Point{sig}}\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 188,
    "end_line": 194,
    "claim": "GetPubKeyG2 derives the G2 public key on demand by multiplying the G2 generator by the private key scalar",
    "section": "API Surface",
    "snippet": "func (k *KeyPair) GetPubKeyG2() *G2Point {\n\treturn &G2Point{MulByGeneratorG2(k.PrivKey)}\n}"
  },
  {
    "file_path": "encoding/v2/kzg/verifier/parametrized_verifier.go",
    "start_line": 8,
    "end_line": 8,
    "claim": "The KZG parametrized verifier imports crypto/ecc/bn254 as 'eigenbn254' to use PairingsVerify for frame proof checking",
    "section": "Architecture",
    "snippet": "eigenbn254 \"github.com/Layr-Labs/eigenda/crypto/ecc/bn254\""
  },
  {
    "file_path": "encoding/v2/kzg/verifier/parametrized_verifier.go",
    "start_line": 85,
    "end_line": 88,
    "claim": "KZG frame verification uses eigenbn254.PairingsVerify to check the KZG evaluation proof pairing equation",
    "section": "Data Flows",
    "snippet": "err = eigenbn254.PairingsVerify(&commitMinusInterpolation, &kzg.GenG2, &frame.Proof, &xnMinusYn)\nif err != nil {\n\treturn fmt.Errorf(\"verify pairing: %w\", err)\n}"
  },
  {
    "file_path": "encoding/v2/kzg/committer/verify_length_proof.go",
    "start_line": 9,
    "end_line": 9,
    "claim": "The length proof verifier imports crypto/ecc/bn254 for PairingsVerify and RandomFrs",
    "section": "Architecture",
    "snippet": "eigenbn254 \"github.com/Layr-Labs/eigenda/crypto/ecc/bn254\""
  },
  {
    "file_path": "encoding/v2/kzg/committer/verify_length_proof.go",
    "start_line": 58,
    "end_line": 62,
    "claim": "eigenbn254.PairingsVerify verifies the low-degree length proof by checking e(s^shift G1, p(s)G2) == e(G1, p(s^shift)G2)",
    "section": "Data Flows",
    "snippet": "err := eigenbn254.PairingsVerify(&g1Challenge, lengthCommit, &kzg.GenG1, lengthProof)\nif err != nil {\n\treturn fmt.Errorf(\"verify pairing: %w\", err)\n}"
  },
  {
    "file_path": "encoding/v2/kzg/committer/verify_length_proof.go",
    "start_line": 96,
    "end_line": 97,
    "claim": "RandomFrs provides the random linear combination coefficients for batch commitment equivalence verification",
    "section": "Data Flows",
    "snippet": "randomsFr, err := eigenbn254.RandomFrs(len(g1commits))\nif err != nil {\n\treturn fmt.Errorf(\"create randomness vector: %w\", err)\n}"
  },
  {
    "file_path": "go.mod",
    "start_line": 32,
    "end_line": 32,
    "claim": "gnark-crypto is pinned to v0.18.0, the core dependency for all BN254 elliptic curve arithmetic",
    "section": "Dependencies",
    "snippet": "github.com/consensys/gnark-crypto v0.18.0"
  },
  {
    "file_path": "go.mod",
    "start_line": 36,
    "end_line": 36,
    "claim": "go-ethereum is pinned to v1.15.3 (replaced by op-geth) providing Keccak256, common.Address, and math.U256Bytes",
    "section": "Dependencies",
    "snippet": "github.com/ethereum/go-ethereum v1.15.3"
  },
  {
    "file_path": "go.mod",
    "start_line": 20,
    "end_line": 20,
    "claim": "go-ethereum is replaced by op-geth (ethereum-optimism fork) to align with EigenDA's OP stack integration",
    "section": "Dependencies",
    "snippet": "replace github.com/ethereum/go-ethereum => github.com/ethereum-optimism/op-geth v1.101511.1"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 63,
    "end_line": 68,
    "claim": "G1Point.Clone performs a deep copy by extracting BigInt coordinates and re-constructing fp.Elements, avoiding aliasing issues",
    "section": "Key Components",
    "snippet": "func (p *G1Point) Clone() *G1Point {\n\treturn &G1Point{&bn254.G1Affine{\n\t\tX: newFpElement(p.X.BigInt(new(big.Int))),\n\t\tY: newFpElement(p.Y.BigInt(new(big.Int))),\n\t}}\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 70,
    "end_line": 72,
    "claim": "G1Point.Hash returns a keccak256 of the serialized point bytes for use as a compact identifier",
    "section": "Key Components",
    "snippet": "func (p *G1Point) Hash() [32]byte {\n\treturn crypto.Keccak256Hash(p.Serialize())\n}"
  },
  {
    "file_path": "crypto/ecc/bn254/attestation.go",
    "start_line": 196,
    "end_line": 203,
    "claim": "KeyPair.MakePubkeyRegistrationData wraps the package-level function with the same name, exposing it as a method on KeyPair for convenience",
    "section": "API Surface",
    "snippet": "func (k *KeyPair) MakePubkeyRegistrationData(operatorAddress common.Address) *G1Point {\n\treturn &G1Point{MakePubkeyRegistrationData(k.PrivKey, operatorAddress)}\n}"
  }
]
```

## Analysis Notes

### Security Considerations

1. **Try-and-increment hash-to-curve is timing-variable**: The `MapToCurve` function's loop terminates after a variable number of iterations depending on the input, which can leak information about the message via timing side-channels. A constant-time hash-to-curve (e.g., the IETF hash-to-curve standard, RFC 9380) would be preferable in adversarial environments where timing oracles are possible. However, since this matches the on-chain Solidity contract's behavior, changing it requires a coordinated upgrade.

2. **Rogue-key attack prevention**: The `MakePubkeyRegistrationData` function correctly implements proof-of-possession to prevent rogue-key (or key cancellation) attacks in the BLS multi-signature setting. By requiring operators to sign their own Ethereum address under a domain-separated type string, EigenDA prevents an adversary from registering `pubkey = -honest_pubkey` to cancel out honest operators in aggregate signatures.

3. **Use of `crypto/rand` for entropy**: Both `GenRandomBlsKeys` and `randomFr` correctly use Go's `crypto/rand` (the OS CSPRNG) rather than `math/rand`, ensuring private keys and batch verification randomness are cryptographically unpredictable.

4. **Type alias for PrivateKey**: `type PrivateKey = fr.Element` is a type alias, not a distinct type. This means private key material can accidentally be passed to functions expecting field elements without compiler type-checking. A distinct type (`type PrivateKey fr.Element`) would provide stronger type safety at the cost of requiring explicit conversions.

5. **Architectural duplication risk**: The near-identical copy of this logic in `core/bn254/attestation.go` creates a maintenance hazard — security fixes must be applied in both locations. The two implementations should ideally be unified.

### Performance Characteristics

- **Pairing check cost**: `PairingsVerify` and `VerifySig` call `bn254.PairingCheck`, which is the most computationally expensive operation (typically ~10-20ms per pairing on modern hardware without GPU acceleration). This is by design in pairing-based cryptography.
- **Batch verification efficiency**: `RandomFrs` generates a power-of-`r` vector using a single random seed, allowing `batchVerifyCommitEquivalence` to collapse N pairings into one via multi-scalar exponentiation — a significant speedup over N individual verifications.
- **MapToCurve non-constant time**: The try-and-increment loop averages ~2 iterations (each field element is a quadratic residue with probability ~1/2), but is unbounded. For 32-byte random inputs this is expected to terminate very quickly in practice.

### Scalability Notes

- **Stateless design**: All functions are stateless and free of shared mutable state, making the library safe for concurrent use across multiple goroutines without synchronization.
- **No caching of generator points**: Generator points are recomputed on every call to `GetG1Generator` / `GetG2Generator`. Caching these as package-level variables would improve performance for high-throughput signing scenarios.
- **Multi-exponentiation**: The KZG consumers use gnark-crypto's `MultiExp` (multi-scalar exponentiation) which uses Pippenger's algorithm for efficient batch operations — a critical optimization for verifying many frames simultaneously in the relay and verifier components.
