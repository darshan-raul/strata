# Keycloak

> **Stub for Phase 0.** Full doc lands in Phase 2.

[Keycloak](https://www.keycloak.org/) is the OIDC provider
Strata runs in the backend to authenticate users. Replaces the
v1 plan's Zitadel.

Why Keycloak over Zitadel:

- Wider deployment, more battle-tested
- Better Helm chart (`bitnami/keycloak` or the official
  `quay.io/keycloak/keycloak` chart)
- Mature OIDC + OAuth2 + SAML support
- Admin UI included
- Realm-per-environment pattern for staging / dev / prod
  isolation

In the backend, Keycloak is the source of truth for user
identity. The orchestrator validates Keycloak-issued JWTs via
Envoy Gateway's `jwt_authn` HTTP filter (see
`docs/envoy-gateway.md`). The TUI authenticates with the OIDC
device-code flow against Keycloak, with the user typing the
device-code URL into the web dashboard.

Planned outline:

1. The OIDC mental model (IdP, Relying Party, tokens)
2. Device-code flow (TUI ↔ Keycloak ↔ web)
3. Auth-code flow (web ↔ Keycloak)
4. JWT structure and validation
5. Realm configuration (clients, scopes, mappers)
6. Helm chart deployment
7. Admin UI access
8. Keycloak as the OIDC source of truth (no other auth)
9. What to read next