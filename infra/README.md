# Strata infra

> **Stub for Phase 0.** The Terraform lands in Phase 8.

The Terraform that bootstraps the backend Kubernetes cluster
(EKS).

```
infra/
├── bootstrap/   # VPC, EKS, S3 TF state, KMS, ACM, IRSA
└── modules/     # reusable Terraform modules
```

## Phase 8 plan

1. VPC (public + private subnets across 3 AZs)
2. EKS (managed node groups + Karpenter)
3. S3 bucket for Terraform state + DynamoDB for locking
4. KMS keys for:
   - Terraform state encryption
   - Cluster-credential DEK wrapping (Phase 4)
   - EBS encryption (Postgres volumes)
5. ACM certificate for the Strata ingress
6. IRSA roles for each backend service that needs AWS access
   (litellm → Bedrock, external-secrets → Secrets Manager,
   CloudNativePG → S3 backups)

## See also

- `../AGENTS.md`
- `../docs/external-secrets.md`