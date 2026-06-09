package main

import (
	"database/sql"
	"encoding/json"
	"log"
	"math/rand"
	"net/http"
	"os"
	"strings"
	"time"

	_ "github.com/lib/pq"
	"github.com/nats-io/nats.go"
)

var db *sql.DB
var nc *nats.Conn

func env(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func jsonResp(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("encode error: %v", err)
	}
}

func cors(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type,Authorization")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next(w, r)
	}
}

func waitForDB(dsn string) *sql.DB {
	for i := 0; i < 15; i++ {
		d, err := sql.Open("postgres", dsn)
		if err == nil {
			if err = d.Ping(); err == nil {
				log.Println("Connected to Postgres")
				return d
			}
		}
		log.Printf("DB not ready (%d/15), retrying...", i+1)
		time.Sleep(3 * time.Second)
	}
	log.Fatal("Could not connect to Postgres")
	return nil
}

func waitForNATS(url string) *nats.Conn {
	for i := 0; i < 15; i++ {
		c, err := nats.Connect(url)
		if err == nil {
			log.Println("Connected to NATS")
			return c
		}
		log.Printf("NATS not ready (%d/15), retrying...", i+1)
		time.Sleep(2 * time.Second)
	}
	log.Fatal("Could not connect to NATS")
	return nil
}

// ── Provision Request ─────────────────────────────────────────

type ProvisionRequest struct {
	ID           string    `json:"id"`
	Name         string    `json:"name"`
	ResourceType string    `json:"resource_type"`
	Environment  string    `json:"environment"`
	Requester    string    `json:"requester"`
	Status       string    `json:"status"`
	ErrorMessage string    `json:"error_message,omitempty"`
	CreatedAt    time.Time `json:"created_at"`
	UpdatedAt    time.Time `json:"updated_at"`
}

// simulateProvisioning runs the state machine in the background
func simulateProvisioning(id string) {
	log.Printf("[provisioner] starting simulation for %s", id)

	// pending → provisioning
	time.Sleep(time.Duration(2+rand.Intn(3)) * time.Second)
	if _, err := db.Exec(`UPDATE provision_requests SET status='provisioning', updated_at=NOW() WHERE id=$1`, id); err != nil {
		log.Printf("exec error: %v", err)
	}
	payload, _ := json.Marshal(map[string]string{"id": id, "status": "provisioning"})
	if err := nc.Publish("idp.provisioner.request.updated", payload); err != nil {
		log.Printf("publish error: %v", err)
	}
	log.Printf("[provisioner] %s → provisioning", id)

	// provisioning → completed|failed (90% success)
	time.Sleep(time.Duration(5+rand.Intn(8)) * time.Second)
	finalStatus := "completed"
	errMsg := ""
	if rand.Intn(10) == 0 { // 10% failure
		finalStatus = "failed"
		errMsg = "Quota exceeded in target region"
	}
	if _, err := db.Exec(`UPDATE provision_requests SET status=$1, error_message=$2, updated_at=NOW() WHERE id=$3`,
		finalStatus, errMsg, id); err != nil {
		log.Printf("exec error: %v", err)
	}
	payload, _ = json.Marshal(map[string]string{"id": id, "status": finalStatus})
	if err := nc.Publish("idp.provisioner.request."+finalStatus, payload); err != nil {
		log.Printf("publish error: %v", err)
	}
	log.Printf("[provisioner] %s → %s", id, finalStatus)
}

func provisionListHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		rows, err := db.Query(`
			SELECT id, name, resource_type, environment, COALESCE(requester,'system'),
			       status, COALESCE(error_message,''), created_at, updated_at
			FROM provision_requests ORDER BY created_at DESC LIMIT 100`)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		defer rows.Close()
		reqs := []ProvisionRequest{}
		for rows.Next() {
			var p ProvisionRequest
			if err := rows.Scan(&p.ID, &p.Name, &p.ResourceType, &p.Environment,
				&p.Requester, &p.Status, &p.ErrorMessage, &p.CreatedAt, &p.UpdatedAt); err != nil {
				log.Printf("scan error: %v", err)
				continue
			}
			reqs = append(reqs, p)
		}
		jsonResp(w, 200, reqs)

	case http.MethodPost:
		var p ProvisionRequest
		if err := json.NewDecoder(r.Body).Decode(&p); err != nil {
			jsonResp(w, 400, map[string]string{"error": err.Error()})
			return
		}
		if p.Requester == "" {
			p.Requester = "system"
		}
		var id string
		err := db.QueryRow(`
			INSERT INTO provision_requests (name, resource_type, environment, requester)
			VALUES ($1,$2,$3,$4) RETURNING id`,
			p.Name, p.ResourceType, p.Environment, p.Requester).Scan(&id)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		payload, _ := json.Marshal(map[string]string{"id": id, "name": p.Name, "type": p.ResourceType, "env": p.Environment})
		if err := nc.Publish("idp.provisioner.request.created", payload); err != nil {
			log.Printf("publish error: %v", err)
		}
		log.Printf("[provisioner] request created: %s (%s/%s)", p.Name, p.ResourceType, p.Environment)
		go simulateProvisioning(id)
		jsonResp(w, 202, map[string]string{"id": id, "status": "pending"})
	}
}

func provisionByIDHandler(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/provisions/")
	var p ProvisionRequest
	err := db.QueryRow(`
		SELECT id, name, resource_type, environment, COALESCE(requester,'system'),
		       status, COALESCE(error_message,''), created_at, updated_at
		FROM provision_requests WHERE id=$1`, id).Scan(
		&p.ID, &p.Name, &p.ResourceType, &p.Environment, &p.Requester,
		&p.Status, &p.ErrorMessage, &p.CreatedAt, &p.UpdatedAt)
	if err == sql.ErrNoRows {
		jsonResp(w, 404, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	jsonResp(w, 200, p)
}

func statsHandler(w http.ResponseWriter, r *http.Request) {
	var total, pending, provisioning, completed, failed int
	if err := db.QueryRow(`SELECT COUNT(*) FROM provision_requests`).Scan(&total); err != nil {
		log.Printf("count total error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM provision_requests WHERE status='pending'`).Scan(&pending); err != nil {
		log.Printf("count pending error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM provision_requests WHERE status='provisioning'`).Scan(&provisioning); err != nil {
		log.Printf("count provisioning error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM provision_requests WHERE status='completed'`).Scan(&completed); err != nil {
		log.Printf("count completed error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM provision_requests WHERE status='failed'`).Scan(&failed); err != nil {
		log.Printf("count failed error: %v", err)
	}
	jsonResp(w, 200, map[string]int{
		"total": total, "pending": pending, "provisioning": provisioning,
		"completed": completed, "failed": failed,
	})
}

func main() {
	log.SetFlags(log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[provisioner-service] ")
	log.Println("Starting...")

	db = waitForDB(env("DB_DSN", "postgres://strata:strata_password@postgres:5432/strata?sslmode=disable"))
	nc = waitForNATS(env("NATS_URL", "nats://nats:4222"))

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, 200, map[string]string{"status": "ok", "service": "provisioner-service"})
	})
	mux.HandleFunc("/provisions", cors(provisionListHandler))
	mux.HandleFunc("/provisions/", cors(provisionByIDHandler))
	mux.HandleFunc("/provisions/stats", cors(statsHandler))

	port := env("PORT", "8082")
	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
