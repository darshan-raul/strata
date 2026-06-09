{{/*
Expand the name of this chart
*/}}
{{- define "strata.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create the namespace
*/}}
{{- define "strata.namespace" -}}
{{- .Values.namespace }}
{{- end }}

{{/*
Postgres DNS name
*/}}
{{- define "strata.postgres.url" -}}
{{- printf "postgres://%s:%s@postgres:5432/%s?sslmode=disable" .Values.postgres.env.user .Values.postgres.env.password .Values.postgres.env.database }}
{{- end }}

{{/*
Nats URL
*/}}
{{- define "strata.nats.url" -}}
{{- printf "nats://nats:4222" }}
{{- end }}