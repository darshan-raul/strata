package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/nats-io/nats.go"
)

type DeploymentRequest struct {
	DeploymentID string    `json:"deployment_id"`
	Service      string    `json:"service"`
	ImageTag     string    `json:"image_tag"`
	Environments []string  `json:"environments"`
	Strategy     string    `json:"strategy"`
	SubmittedBy  string    `json:"submitted_by"`
	SubmittedAt  time.Time `json:"submitted_at"`
}

type ApprovalDecision struct {
	DeploymentID string            `json:"deployment_id"`
	Approved     bool              `json:"approved"`
	Reason       string            `json:"reason"`
	Request      DeploymentRequest `json:"request"`
}

type ExecutionPlan struct {
	DeploymentID string `json:"deployment_id"`
	Service      string `json:"service"`
	ImageTag     string `json:"image_tag"`
	Cloud        string `json:"cloud"` // e.g., "aws" or "gcp"
	Strategy     string `json:"strategy"`
}

var nc *nats.Conn
var js nats.JetStreamContext

func initNATS() {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}
	
	var err error
	for i := 0; i < 5; i++ {
		nc, err = nats.Connect(natsURL)
		if err == nil {
			break
		}
		log.Printf("Failed to connect to NATS, retrying... (%v)", err)
		time.Sleep(2 * time.Second)
	}
	if err != nil {
		log.Fatalf("Fatal error connecting to NATS: %v", err)
	}

	js, err = nc.JetStream()
	if err != nil {
		log.Fatalf("Fatal error getting JetStream context: %v", err)
	}
}

func handleApprovedEvent(msg *nats.Msg) {
	var decision ApprovalDecision
	if err := json.Unmarshal(msg.Data, &decision); err != nil {
		log.Printf("Error unmarshaling ApprovalDecision: %v", err)
		msg.Nak()
		return
	}

	if !decision.Approved {
		log.Printf("Deployment %s was rejected. Skipping rollout planner.", decision.DeploymentID)
		msg.Ack()
		return
	}

	log.Printf("Planning rollout for %s (Service: %s)...", decision.DeploymentID, decision.Request.Service)

	// In a real app, query DB to map environments to clouds.
	// For demo, we fan out to both AWS (EKS) and GCP (GKE).
	clouds := []string{"aws", "gcp"}

	for _, cloud := range clouds {
		plan := ExecutionPlan{
			DeploymentID: decision.DeploymentID,
			Service:      decision.Request.Service,
			ImageTag:     decision.Request.ImageTag,
			Cloud:        cloud,
			Strategy:     decision.Request.Strategy,
		}

		payload, _ := json.Marshal(plan)
		
		_, err := js.Publish("deployments.planned", payload)
		if err != nil {
			log.Printf("Error publishing execution plan: %v", err)
			msg.Nak()
			return
		}
		log.Printf("Published deployments.planned for %s targeting %s", decision.DeploymentID, cloud)
	}

	msg.Ack()
}

func startConsumer() {
	_, err := js.QueueSubscribe("deployments.approved", "rollout_planner_group", handleApprovedEvent, nats.ManualAck())
	if err != nil {
		log.Fatalf("Error subscribing to approved events: %v", err)
	}
	log.Printf("Listening for deployments.approved...")
}

func main() {
	log.Printf("Starting rollout-planner...")
	initNATS()
	startConsumer()
	
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})
	
	log.Fatal(http.ListenAndServe(":8080", nil))
}
