package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	_ "github.com/lib/pq"
	"github.com/nats-io/nats.go"
	"github.com/redis/go-redis/v9"
)

var db *sql.DB
var nc *nats.Conn
var rdb *redis.Client
var ctx = context.Background()

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
		w.Header().Set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
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
		log.Printf("DB not ready (%d/15)...", i+1)
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
		log.Printf("NATS not ready (%d/15)...", i+1)
		time.Sleep(2 * time.Second)
	}
	log.Fatal("Could not connect to NATS")
	return nil
}

// ── Workflow Definitions ──────────────────────────────────────

type WorkflowDef struct {
	Steps []string
}

var workflowDefs = map[string]WorkflowDef{
	"service-onboarding": {Steps: []string{
		"Register in catalog",
		"Create Kubernetes namespace",
		"Provision database",
		"Configure monitoring",
		"Generate scorecard",
		"Notify team",
	}},
	"resource-provisioning": {Steps: []string{
		"Validate request",
		"Check quota limits",
		"Provision infrastructure",
		"Configure networking",
		"Run health checks",
	}},
	"service-decommission": {Steps: []string{
		"Flag for decommission",
		"Notify dependent services",
		"Drain traffic",
		"Backup data",
		"Deprovision resources",
		"Archive catalog entry",
	}},
	"environment-rollout": {Steps: []string{
		"Validate manifests",
		"Deploy to staging",
		"Run smoke tests",
		"Promote to production",
		"Verify rollout",
	}},
}

// ── Types ─────────────────────────────────────────────────────

type Workflow struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Type        string    `json:"type"`
	Status      string    `json:"status"`
	EntityID    string    `json:"entity_id"`
	EntityType  string    `json:"entity_type"`
	CurrentStep int       `json:"current_step"`
	TotalSteps  int       `json:"total_steps"`
	Steps       []Step    `json:"steps,omitempty"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type Step struct {
	ID          string     `json:"id"`
	WorkflowID  string     `json:"workflow_id"`
	StepNumber  int        `json:"step_number"`
	Name        string     `json:"name"`
	Status      string     `json:"status"`
	Output      string     `json:"output"`
	StartedAt   *time.Time `json:"started_at"`
	CompletedAt *time.Time `json:"completed_at"`
}

func mustMarshal(v any) []byte {
	b, _ := json.Marshal(v)
	return b
}

func runWorkflow(workflowID string, def WorkflowDef) {
	log.Printf("running workflow %s (%d steps)", workflowID, len(def.Steps))
	if _, err := db.Exec(`UPDATE workflows SET status='running', updated_at=NOW() WHERE id=$1`, workflowID); err != nil {
		log.Printf("exec error: %v", err)
	}
	if err := nc.Publish("idp.workflow.started", mustMarshal(map[string]string{"id": workflowID})); err != nil {
		log.Printf("publish error: %v", err)
	}

	for i, stepName := range def.Steps {
		stepNum := i + 1
		now := time.Now()
		if _, err := db.Exec(`UPDATE workflow_steps SET status='running', started_at=$1 WHERE workflow_id=$2 AND step_number=$3`,
			now, workflowID, stepNum); err != nil {
			log.Printf("exec error: %v", err)
		}
		if _, err := db.Exec(`UPDATE workflows SET current_step=$1, updated_at=NOW() WHERE id=$2`, stepNum, workflowID); err != nil {
			log.Printf("exec error: %v", err)
		}
		rdb.HSet(ctx, "workflow:"+workflowID, "current_step", stepNum, "step_name", stepName)

		time.Sleep(time.Duration(2+stepNum) * time.Second)

		done := time.Now()
		if _, err := db.Exec(`UPDATE workflow_steps SET status='completed', output='Completed successfully', completed_at=$1 WHERE workflow_id=$2 AND step_number=$3`,
			done, workflowID, stepNum); err != nil {
			log.Printf("exec error: %v", err)
		}
		if err := nc.Publish("idp.workflow.step.completed", mustMarshal(map[string]any{
			"workflow_id": workflowID, "step": stepNum, "name": stepName,
		})); err != nil {
			log.Printf("publish error: %v", err)
		}
		log.Printf("workflow %s step %d/%d ✓ %s", workflowID, stepNum, len(def.Steps), stepName)
	}

	if _, err := db.Exec(`UPDATE workflows SET status='completed', current_step=$1, updated_at=NOW() WHERE id=$2`,
		len(def.Steps), workflowID); err != nil {
		log.Printf("exec error: %v", err)
	}
	rdb.HSet(ctx, "workflow:"+workflowID, "status", "completed")
	rdb.Expire(ctx, "workflow:"+workflowID, 1*time.Hour)
	if err := nc.Publish("idp.workflow.completed", mustMarshal(map[string]string{"id": workflowID})); err != nil {
		log.Printf("publish error: %v", err)
	}
	log.Printf("workflow %s completed", workflowID)
}

func workflowsHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		rows, err := db.Query(`
			SELECT id, name, type, status, COALESCE(entity_id,''), COALESCE(entity_type,''),
			       current_step, total_steps, created_at, updated_at
			FROM workflows ORDER BY created_at DESC LIMIT 50`)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		defer rows.Close()
		wfs := []Workflow{}
		for rows.Next() {
			var wf Workflow
			if err := rows.Scan(&wf.ID, &wf.Name, &wf.Type, &wf.Status, &wf.EntityID, &wf.EntityType,
				&wf.CurrentStep, &wf.TotalSteps, &wf.CreatedAt, &wf.UpdatedAt); err != nil {
				log.Printf("scan error: %v", err)
				continue
			}
			wfs = append(wfs, wf)
		}
		jsonResp(w, 200, wfs)

	case http.MethodPost:
		var req struct {
			Type       string `json:"type"`
			EntityID   string `json:"entity_id"`
			EntityType string `json:"entity_type"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			jsonResp(w, 400, map[string]string{"error": err.Error()})
			return
		}
		def, ok := workflowDefs[req.Type]
		if !ok {
			jsonResp(w, 400, map[string]string{"error": "unknown workflow type: " + req.Type})
			return
		}
		var id string
		err := db.QueryRow(`
			INSERT INTO workflows (name, type, entity_id, entity_type, total_steps)
			VALUES ($1,$2,$3,$4,$5) RETURNING id`,
			req.Type, req.Type, req.EntityID, req.EntityType, len(def.Steps)).Scan(&id)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		for i, name := range def.Steps {
			db.Exec(`INSERT INTO workflow_steps (workflow_id, step_number, name) VALUES ($1,$2,$3)`,
				id, i+1, name)
		}
		log.Printf("created %s workflow %s", req.Type, id)
		go runWorkflow(id, def)
		jsonResp(w, 202, map[string]string{"id": id, "type": req.Type, "status": "running"})
	}
}

func workflowByIDHandler(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/workflows/")
	var wf Workflow
	err := db.QueryRow(`
		SELECT id, name, type, status, COALESCE(entity_id,''), COALESCE(entity_type,''),
		       current_step, total_steps, created_at, updated_at
		FROM workflows WHERE id=$1`, id).Scan(
		&wf.ID, &wf.Name, &wf.Type, &wf.Status, &wf.EntityID, &wf.EntityType,
		&wf.CurrentStep, &wf.TotalSteps, &wf.CreatedAt, &wf.UpdatedAt)
	if err == sql.ErrNoRows {
		jsonResp(w, 404, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	rows, _ := db.Query(`
		SELECT id, workflow_id, step_number, name, status, COALESCE(output,''),
		       started_at, completed_at
		FROM workflow_steps WHERE workflow_id=$1 ORDER BY step_number`, id)
	if rows != nil {
		defer rows.Close()
		for rows.Next() {
			var s Step
			if err := rows.Scan(&s.ID, &s.WorkflowID, &s.StepNumber, &s.Name, &s.Status,
				&s.Output, &s.StartedAt, &s.CompletedAt); err != nil {
				log.Printf("scan error: %v", err)
				continue
			}
			wf.Steps = append(wf.Steps, s)
		}
	}
	jsonResp(w, 200, wf)
}

func workflowTypesHandler(w http.ResponseWriter, r *http.Request) {
	types := []map[string]any{}
	for k, v := range workflowDefs {
		types = append(types, map[string]any{"type": k, "steps": v.Steps, "step_count": len(v.Steps)})
	}
	jsonResp(w, 200, types)
}

func statsHandler(w http.ResponseWriter, r *http.Request) {
	var total, running, completed, pending int
	if err := db.QueryRow(`SELECT COUNT(*) FROM workflows`).Scan(&total); err != nil {
		log.Printf("count total error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM workflows WHERE status='running'`).Scan(&running); err != nil {
		log.Printf("count running error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM workflows WHERE status='completed'`).Scan(&completed); err != nil {
		log.Printf("count completed error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM workflows WHERE status='pending'`).Scan(&pending); err != nil {
		log.Printf("count pending error: %v", err)
	}
	jsonResp(w, 200, map[string]int{
		"total": total, "running": running, "completed": completed, "pending": pending,
	})
}

func main() {
	log.SetFlags(log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[workflow-engine] ")
	log.Println("Starting...")

	db = waitForDB(env("DB_DSN", "postgres://accio:accio_password@postgres:5432/accio?sslmode=disable"))
	nc = waitForNATS(env("NATS_URL", "nats://nats:4222"))

	rdb = redis.NewClient(&redis.Options{Addr: env("REDIS_ADDR", "redis:6379")})
	for i := 0; i < 10; i++ {
		if err := rdb.Ping(ctx).Err(); err == nil {
			log.Println("Connected to Redis")
			break
		}
		log.Printf("Redis not ready (%d/10)...", i+1)
		time.Sleep(2 * time.Second)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, 200, map[string]string{"status": "ok", "service": "workflow-engine"})
	})
	mux.HandleFunc("/workflows", cors(workflowsHandler))
	mux.HandleFunc("/workflows/types", cors(workflowTypesHandler))
	mux.HandleFunc("/workflows/stats", cors(statsHandler))
	mux.HandleFunc("/workflows/", cors(workflowByIDHandler))

	port := env("PORT", "8084")
	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
