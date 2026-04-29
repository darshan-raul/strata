package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/nats-io/nats.go"
)

type ExecutionPlan struct {
	DeploymentID string `json:"deployment_id"`
	Service      string `json:"service"`
	ImageTag     string `json:"image_tag"`
	Cloud        string `json:"cloud"`
	Strategy     string `json:"strategy"`
}

var nc *nats.Conn
var js nats.JetStreamContext
var provider string

func initNATS() {
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = nats.DefaultURL
	}
	
	provider = os.Getenv("CLOUD_PROVIDER")
	if provider == "" {
		provider = "aws" // default to aws for eks
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

func handlePlannedEvent(msg *nats.Msg) {
	var plan ExecutionPlan
	if err := json.Unmarshal(msg.Data, &plan); err != nil {
		log.Printf("Error unmarshaling ExecutionPlan: %v", err)
		msg.Nak()
		return
	}

	if plan.Cloud != provider {
		// Not for us
		log.Printf("Ignoring plan for %s (target cloud: %s, our cloud: %s)", plan.DeploymentID, plan.Cloud, provider)
		msg.Ack()
		return
	}

	log.Printf("✅ EXECUTING: Applying Helm chart for %s to EKS cluster! (Tag: %s, Strategy: %s)", 
		plan.Service, plan.ImageTag, plan.Strategy)
	
	// Simulate rollout time
	time.Sleep(3 * time.Second)

	log.Printf("✅ SUCCESS: %s successfully rolled out to EKS.", plan.Service)

	// Here we would publish deployments.completed or healthchecks.failing depending on rollout status.
	
	msg.Ack()
}

func startConsumer() {
	_, err := js.QueueSubscribe("deployments.planned", "eks_executor_group", handlePlannedEvent, nats.ManualAck())
	if err != nil {
		log.Fatalf("Error subscribing to planned events: %v", err)
	}
	log.Printf("Listening for deployments.planned targeting %s...", provider)
}

func main() {
	log.Printf("Starting eks-executor...")
	initNATS()
	startConsumer()
	
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})
	
	log.Fatal(http.ListenAndServe(":8080", nil))
}
