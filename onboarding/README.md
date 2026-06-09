# Strata Onboarding

CloudFormation templates that customers deploy to their AWS account to grant
Strata cross-account access.

## Files

- `strata-platform-role.yaml` — main stack. Creates the `strata-platform-provisioner`
  and `strata-platform-reader` roles. Customers launch this once via the Strata
  onboarding wizard.
- `policies/` — raw IAM policy documents (reference for v2 least-privilege work).

## Deploy

```bash
aws cloudformation create-stack \
  --stack-name strata-platform-roles \
  --template-body file://strata-platform-role.yaml \
  --parameters ParameterKey=StrataAccountId,ParameterValue=123456789012 \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

The stack outputs the ARNs of both roles. The customer pastes the
`ProvisionerRoleArn` back into Strata to complete onboarding.

## How Strata uses these roles

| Role | Assumed by | Purpose |
|---|---|---|
| `strata-platform-provisioner` | `provisioner-worker` (Go k8s Job) via IRSA | Runs `terraform apply` / `terraform destroy` against the customer account |
| `strata-platform-reader` | `status-poller` (Go Deployment) via IRSA | Polls EKS, CloudWatch metrics, CloudWatch logs for cluster health |

External IDs prevent confused-deputy attacks. The customer should not need to
know them — they are baked into the templates. If the customer needs to rotate
the external ID, see the `v2` migration notes in `strata-platform-role.yaml`.

## Migration from v1 (AdministratorAccess)

The original template granted `AdministratorAccess` to the provisioner role.
This is scoped down to explicit `eks:*`, `ec2:*`, and a narrow `iam:*` allow-list
in v2. The `AdministratorAccess` grant was removed in Phase 0 of the rewrite.
