{{/*
Expand the name of this chart
*/}}
{{- define "accio.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name
*/}}
{{- define "accio.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create the namespace
*/}}
{{- define "accio.namespace" -}}
{{- .Values.namespace }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "accio.labels" -}}
app.kubernetes.io/name: {{ include "accio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "accio.selectorLabels" -}}
app.kubernetes.io/name: {{ include "accio.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Postgres DNS name
*/}}
{{- define "accio.postgres.url" -}}
{{- printf "postgres://%s:%s@postgres:5432/%s?sslmode=disable" .Values.postgres.env.user .Values.postgres.env.password .Values.postgres.env.database }}
{{- end }}

{{/*
Nats URL
*/}}
{{- define "accio.nats.url" -}}
{{- printf "nats://nats:4222" }}
{{- end }}