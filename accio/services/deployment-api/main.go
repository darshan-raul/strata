package main

import (
	"encoding/json"
	"fmt"
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

func deployHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req DeploymentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	req.DeploymentID = fmt.Sprintf("dep-%d", time.Now().UnixNano())
	req.SubmittedAt = time.Now()
	
	// Default values
	if req.SubmittedBy == "" {
		req.SubmittedBy = "api-user"
	}
	if req.Strategy == "" {
		req.Strategy = "rolling"
	}

	payload, _ := json.Marshal(req)
	
	// Publish to JetStream
	_, err := js.Publish("deployments.requested", payload)
	if err != nil {
		log.Printf("Error publishing event: %v", err)
		http.Error(w, "Failed to publish event", http.StatusInternalServerError)
		return
	}

	log.Printf("Published deployments.requested for %s", req.DeploymentID)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusAccepted)
	json.NewEncoder(w).Encode(map[string]string{
		"deployment_id": req.DeploymentID,
		"status":        "requested",
	})
}

func main() {
	log.Printf("Starting deployment-api...")
	initNATS()
	
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})
	http.HandleFunc("/deployments", deployHandler)
	
	log.Fatal(http.ListenAndServe(":8080", nil))
}
