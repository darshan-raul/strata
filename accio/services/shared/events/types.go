package events

import "time"

// DeploymentRequest is published by deployment-api on 'deployments.requested'
type DeploymentRequest struct {
	DeploymentID string    `json:"deployment_id"`
	Service      string    `json:"service"`
	ImageTag     string    `json:"image_tag"`
	Environments []string  `json:"environments"`
	Strategy     string    `json:"strategy"`
	SubmittedBy  string    `json:"submitted_by"`
	SubmittedAt  time.Time `json:"submitted_at"`
}

// ApprovalDecision is published by approval-engine on 'deployments.approved' or 'deployments.rejected'
type ApprovalDecision struct {
	DeploymentID string `json:"deployment_id"`
	Approved     bool   `json:"approved"`
	Reason       string `json:"reason"`
}

// ExecutionPlan is published by rollout-planner on 'deployments.planned'
type ExecutionPlan struct {
	DeploymentID string `json:"deployment_id"`
	Service      string `json:"service"`
	ImageTag     string `json:"image_tag"`
	Cloud        string `json:"cloud"`
	Strategy     string `json:"strategy"`
}
