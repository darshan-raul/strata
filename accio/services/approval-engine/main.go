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

	// Create stream if it doesn't exist
	_, err = js.StreamInfo("DEPLOYMENTS")
	if err != nil {
		_, err = js.AddStream(&nats.StreamConfig{
			Name:     "DEPLOYMENTS",
			Subjects: []string{"deployments.>"},
		})
		if err != nil {
			log.Fatalf("Error creating stream: %v", err)
		}
	}
}

func handleRequestedEvent(msg *nats.Msg) {
	var req DeploymentRequest
	if err := json.Unmarshal(msg.Data, &req); err != nil {
		log.Printf("Error unmarshaling DeploymentRequest: %v", err)
		msg.Nak()
		return
	}

	log.Printf("Received deployment request for %s. Evaluating...", req.DeploymentID)

	// In a real app, call the policy-engine OPA here.
	// For Phase 2, we will auto-approve everything.
	decision := ApprovalDecision{
		DeploymentID: req.DeploymentID,
		Approved:     true,
		Reason:       "Auto-approved by default policy",
		Request:      req,
	}

	payload, _ := json.Marshal(decision)
	
	// Publish to JetStream
	_, err := js.Publish("deployments.approved", payload)
	if err != nil {
		log.Printf("Error publishing approved event: %v", err)
		msg.Nak()
		return
	}

	log.Printf("Published deployments.approved for %s", req.DeploymentID)
	msg.Ack()
}

func startConsumer() {
	_, err := js.QueueSubscribe("deployments.requested", "approval_engine_group", handleRequestedEvent, nats.ManualAck())
	if err != nil {
		log.Fatalf("Error subscribing to requested events: %v", err)
	}
	log.Printf("Listening for deployments.requested...")
}

func main() {
	log.Printf("Starting approval-engine...")
	initNATS()
	startConsumer()
	
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})
	
	log.Fatal(http.ListenAndServe(":8080", nil))
}
