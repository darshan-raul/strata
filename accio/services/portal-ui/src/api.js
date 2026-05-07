// Central API client — reads service URLs from Vite env vars
const CATALOG    = import.meta.env.VITE_CATALOG_URL    || 'http://localhost:8081'
const PROV       = import.meta.env.VITE_PROVISIONER_URL || 'http://localhost:8082'
const SCORE      = import.meta.env.VITE_SCORECARD_URL   || 'http://localhost:8083'
const WORKFLOW   = import.meta.env.VITE_WORKFLOW_URL    || 'http://localhost:8084'
const AUDIT      = import.meta.env.VITE_AUDIT_URL       || 'http://localhost:8085'

async function get(base, path) {
  const r = await fetch(`${base}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

async function post(base, path, body) {
  const r = await fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

// Catalog
export const getCatalogServices = () => get(CATALOG, '/catalog/services')
export const getCatalogTeams    = () => get(CATALOG, '/catalog/teams')
export const getCatalogStats    = () => get(CATALOG, '/catalog/stats')
export const createCatalogService = (svc) => post(CATALOG, '/catalog/services', svc)
export const createCatalogTeam    = (team) => post(CATALOG, '/catalog/teams', team)

// Provisioner
export const getProvisions     = () => get(PROV, '/provisions')
export const getProvisionStats = () => get(PROV, '/provisions/stats')
export const createProvision   = (req) => post(PROV, '/provisions', req)

// Scorecards
export const getScorecards   = () => get(SCORE, '/scorecards')
export const refreshScorecard = () => post(SCORE, '/scorecards/refresh', {})

// Workflows
export const getWorkflows      = () => get(WORKFLOW, '/workflows')
export const getWorkflowTypes  = () => get(WORKFLOW, '/workflows/types')
export const getWorkflowStats  = () => get(WORKFLOW, '/workflows/stats')
export const getWorkflowById   = (id) => get(WORKFLOW, `/workflows/${id}`)
export const createWorkflow    = (req) => post(WORKFLOW, '/workflows', req)

// Audit
export const getAuditEvents = (params = '') => get(AUDIT, `/audit${params ? '?' + params : ''}`)
export const getAuditStats  = () => get(AUDIT, '/audit/stats')
