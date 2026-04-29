CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE deployments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    service VARCHAR(255) NOT NULL,
    image_tag VARCHAR(255) NOT NULL,
    environments TEXT[] NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    submitted_by VARCHAR(255) NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE deployment_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    deployment_id UUID NOT NULL REFERENCES deployments(id),
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE environments (
    name VARCHAR(255) PRIMARY KEY,
    cloud VARCHAR(50) NOT NULL,
    cluster VARCHAR(255) NOT NULL,
    current_versions JSONB DEFAULT '{}',
    locked BOOLEAN DEFAULT FALSE,
    lock_reason TEXT
);

CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    deployment_id UUID NOT NULL REFERENCES deployments(id),
    required_approvers TEXT[] NOT NULL,
    approved_by TEXT[] DEFAULT '{}',
    status VARCHAR(50) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE policies (
    name VARCHAR(255) PRIMARY KEY,
    rego_source TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team VARCHAR(255) NOT NULL,
    scopes TEXT[] NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);
