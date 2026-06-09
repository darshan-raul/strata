package main

import (
	"database/sql"
	"encoding/json"
	"log"
	"net/http"
	"os"
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
		w.Header().Set("Access-Control-Allow-Methods", "GET,OPTIONS")
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

// ── Audit Event ───────────────────────────────────────────────

type AuditEvent struct {
	ID         string    `json:"id"`
	EventType  string    `json:"event_type"`
	EntityType string    `json:"entity_type"`
	EntityID   string    `json:"entity_id"`
	Actor      string    `json:"actor"`
	Summary    string    `json:"summary"`
	CreatedAt  time.Time `json:"created_at"`
}

// subjectToEntityType maps NATS subjects to entity types
func subjectToMeta(subject string) (entityType, summary string) {
	m := map[string][2]string{
		"idp.catalog.service.created":         {"catalog_service", "New service registered in catalog"},
		"idp.catalog.team.created":            {"catalog_team", "New team created in catalog"},
		"idp.provisioner.request.created":     {"provision_request", "Provisioning request submitted"},
		"idp.provisioner.request.updated":     {"provision_request", "Provisioning request status updated"},
		"idp.provisioner.request.completed":   {"provision_request", "Resource provisioned successfully"},
		"idp.provisioner.request.failed":      {"provision_request", "Provisioning request failed"},
		"idp.workflow.started":                {"workflow", "Workflow execution started"},
		"idp.workflow.step.completed":         {"workflow", "Workflow step completed"},
		"idp.workflow.completed":              {"workflow", "Workflow completed successfully"},
		"idp.scorecard.evaluated":             {"scorecard", "Service scorecard evaluated"},
	}
	if v, ok := m[subject]; ok {
		return v[0], v[1]
	}
	return "system", subject
}

func storeEvent(subject string, data map[string]any) {
	entityType, summary := subjectToMeta(subject)
	entityID := ""
	if id, ok := data["id"].(string); ok {
		entityID = id
	} else if id, ok := data["workflow_id"].(string); ok {
		entityID = id
	} else if id, ok := data["service_id"].(string); ok {
		entityID = id
	}
	actor := "system"
	if a, ok := data["actor"].(string); ok && a != "" {
		actor = a
	}

	_, err := db.Exec(`
		INSERT INTO audit_events (event_type, entity_type, entity_id, actor, summary)
		VALUES ($1,$2,$3,$4,$5)`,
		subject, entityType, entityID, actor, summary)
	if err != nil {
		log.Printf("failed to store audit event: %v", err)
	} else {
		log.Printf("recorded: %s → %s", subject, entityID)
	}
}

func auditHandler(w http.ResponseWriter, r *http.Request) {
	entityType := r.URL.Query().Get("entity_type")
	entityID := r.URL.Query().Get("entity_id")
	limitStr := r.URL.Query().Get("limit")
	limit := 100
	if limitStr != "" {
		if err := json.Unmarshal([]byte(limitStr), &limit); err != nil {
			log.Printf("limit parse error: %v", err)
		}
	}

	query := `SELECT id, event_type, COALESCE(entity_type,''), COALESCE(entity_id,''),
	                 actor, COALESCE(summary,''), created_at
	          FROM audit_events`
	args := []any{}
	where := []string{}

	if entityType != "" {
		args = append(args, entityType)
		where = append(where, "entity_type=$"+string(rune('0'+len(args))))
	}
	if entityID != "" {
		args = append(args, entityID)
		where = append(where, "entity_id=$"+string(rune('0'+len(args))))
	}
	if len(where) > 0 {
		query += " WHERE " + where[0]
		if len(where) > 1 {
			query += " AND " + where[1]
		}
	}
	args = append(args, limit)
	query += " ORDER BY created_at DESC LIMIT $" + string(rune('0'+len(args)))

	rows, err := db.Query(query, args...)
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()
	events := []AuditEvent{}
	for rows.Next() {
		var e AuditEvent
		if err := rows.Scan(&e.ID, &e.EventType, &e.EntityType, &e.EntityID,
			&e.Actor, &e.Summary, &e.CreatedAt); err != nil {
			log.Printf("scan error: %v", err)
			continue
		}
		events = append(events, e)
	}
	jsonResp(w, 200, events)
}

func auditStatsHandler(w http.ResponseWriter, r *http.Request) {
	var total int
	if err := db.QueryRow(`SELECT COUNT(*) FROM audit_events`).Scan(&total); err != nil {
		log.Printf("count total error: %v", err)
	}
	var todayCount int
	if err := db.QueryRow(`SELECT COUNT(*) FROM audit_events WHERE created_at >= NOW() - INTERVAL '24 hours'`).Scan(&todayCount); err != nil {
		log.Printf("count today error: %v", err)
	}

	rows, _ := db.Query(`SELECT event_type, COUNT(*) FROM audit_events GROUP BY event_type ORDER BY COUNT(*) DESC LIMIT 10`)
	byType := map[string]int{}
	if rows != nil {
		defer rows.Close()
		for rows.Next() {
			var t string
			var c int
			if err := rows.Scan(&t, &c); err != nil {
				log.Printf("scan by_type error: %v", err)
				continue
			}
			byType[t] = c
		}
	}
	jsonResp(w, 200, map[string]any{
		"total": total, "last_24h": todayCount, "by_type": byType,
	})
}

func main() {
	log.SetFlags(log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[audit-service] ")
	log.Println("Starting...")

	db = waitForDB(env("DB_DSN", "postgres://Strata:accio_password@postgres:5432/Strata?sslmode=disable"))
	nc = waitForNATS(env("NATS_URL", "nats://nats:4222"))

	// Subscribe to ALL IDP events using wildcard
	subjects := []string{
		"idp.catalog.>",
		"idp.provisioner.>",
		"idp.workflow.>",
		"idp.scorecard.>",
	}
	for _, subj := range subjects {
		s := subj // capture
		if _, err := nc.Subscribe(s, func(msg *nats.Msg) {
			var data map[string]any
			if err := json.Unmarshal(msg.Data, &data); err != nil {
				log.Printf("unmarshal error: %v", err)
				data = map[string]any{}
			}
			if data == nil {
				data = map[string]any{}
			}
			storeEvent(msg.Subject, data)
		}); err != nil {
			log.Printf("subscribe error for %s: %v", s, err)
		}
		log.Printf("subscribed to %s", s)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if err := db.QueryRow(`SELECT 1`).Scan(new(int)); err != nil {
			log.Printf("liveness check error: %v", err)
		}
		jsonResp(w, 200, map[string]string{"status": "ok", "service": "audit-service"})
	})
	mux.HandleFunc("/audit", cors(auditHandler))
	mux.HandleFunc("/audit/stats", cors(auditStatsHandler))

	port := env("PORT", "8085")
	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
