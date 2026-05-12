{{- /*
Authelia secret
*/ -}}
apiVersion: v1
kind: Secret
metadata:
  name: authelia-secret
  namespace: {{ include "accio.namespace" . }}
  labels:
    {{- include "accio.labels" . | nindent 4 }}
type: Opaque
stringData:
  SESSION_SECRET: {{ .Values.authelia.config.sessionSecret }}
  ENCRYPTION_KEY: {{ .Values.authelia.config.encryptionKey }}
  HMAC_SECRET: {{ .Values.authelia.config.hmacSecret }}