package main

import (
	"database/sql"
	"encoding/json"
	"log"
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
	json.NewEncoder(w).Encode(v)
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

// ── Scorecard ─────────────────────────────────────────────────

type Scorecard struct {
	ID               string    `json:"id"`
	ServiceID        string    `json:"service_id"`
	ServiceName      string    `json:"service_name"`
	DocsScore        int       `json:"docs_score"`
	SecurityScore    int       `json:"security_score"`
	ReliabilityScore int       `json:"reliability_score"`
	OwnershipScore   int       `json:"ownership_score"`
	TotalScore       int       `json:"total_score"`
	Grade            string    `json:"grade"`
	EvaluatedAt      time.Time `json:"evaluated_at"`
}

func grade(score int) string {
	switch {
	case score >= 90:
		return "A"
	case score >= 75:
		return "B"
	case score >= 60:
		return "C"
	case score >= 40:
		return "D"
	default:
		return "F"
	}
}

// evaluateService fetches service flags from catalog and computes a score
func evaluateService(serviceID, serviceName string) {
	var hasDocs, hasSLO, hasAPISpec, hasMonitoring bool
	var hasOwner bool

	err := db.QueryRow(`
		SELECT has_docs, has_slo, has_api_spec, has_monitoring,
		       (team_id IS NOT NULL) AS has_owner
		FROM catalog_services WHERE id=$1`, serviceID).
		Scan(&hasDocs, &hasSLO, &hasAPISpec, &hasMonitoring, &hasOwner)
	if err != nil {
		log.Printf("[scorecard] service %s not found in catalog: %v", serviceID, err)
		return
	}

	docsScore := 0
	if hasDocs {
		docsScore = 25
	}
	secScore := 0
	if hasAPISpec {
		secScore = 25
	}
	relScore := 0
	if hasSLO {
		relScore += 15
	}
	if hasMonitoring {
		relScore += 10
	}
	ownScore := 0
	if hasOwner {
		ownScore = 25
	}
	total := docsScore + secScore + relScore + ownScore
	g := grade(total)

	_, err = db.Exec(`
		INSERT INTO scorecards (service_id, service_name, docs_score, security_score, reliability_score, ownership_score, total_score, grade, evaluated_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW())
		ON CONFLICT (service_id) DO UPDATE
		  SET service_name=$2, docs_score=$3, security_score=$4, reliability_score=$5,
		      ownership_score=$6, total_score=$7, grade=$8, evaluated_at=NOW()`,
		serviceID, serviceName, docsScore, secScore, relScore, ownScore, total, g)
	if err != nil {
		log.Printf("[scorecard] upsert failed: %v", err)
		return
	}

	payload, _ := json.Marshal(map[string]any{
		"service_id": serviceID, "service_name": serviceName,
		"total_score": total, "grade": g,
	})
	nc.Publish("idp.scorecard.evaluated", payload)
	log.Printf("[scorecard] evaluated %s → %d (%s)", serviceName, total, g)
}

func scorecardsHandler(w http.ResponseWriter, r *http.Request) {
	rows, err := db.Query(`
		SELECT id, service_id, service_name, docs_score, security_score,
		       reliability_score, ownership_score, total_score, grade, evaluated_at
		FROM scorecards ORDER BY total_score DESC`)
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()
	cards := []Scorecard{}
	for rows.Next() {
		var s Scorecard
		rows.Scan(&s.ID, &s.ServiceID, &s.ServiceName, &s.DocsScore, &s.SecurityScore,
			&s.ReliabilityScore, &s.OwnershipScore, &s.TotalScore, &s.Grade, &s.EvaluatedAt)
		cards = append(cards, s)
	}
	jsonResp(w, 200, cards)
}

func scorecardByServiceHandler(w http.ResponseWriter, r *http.Request) {
	serviceID := strings.TrimPrefix(r.URL.Path, "/scorecards/")
	var s Scorecard
	err := db.QueryRow(`
		SELECT id, service_id, service_name, docs_score, security_score,
		       reliability_score, ownership_score, total_score, grade, evaluated_at
		FROM scorecards WHERE service_id=$1`, serviceID).
		Scan(&s.ID, &s.ServiceID, &s.ServiceName, &s.DocsScore, &s.SecurityScore,
			&s.ReliabilityScore, &s.OwnershipScore, &s.TotalScore, &s.Grade, &s.EvaluatedAt)
	if err == sql.ErrNoRows {
		jsonResp(w, 404, map[string]string{"error": "scorecard not found"})
		return
	}
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	jsonResp(w, 200, s)
}

// refreshAllHandler re-evaluates all services in the catalog
func refreshAllHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		jsonResp(w, 405, map[string]string{"error": "method not allowed"})
		return
	}
	rows, err := db.Query(`SELECT id, name FROM catalog_services`)
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	defer rows.Close()
	count := 0
	for rows.Next() {
		var id, name string
		rows.Scan(&id, &name)
		go evaluateService(id, name)
		count++
	}
	jsonResp(w, 202, map[string]any{"triggered": count, "message": "refresh started"})
}

func main() {
	log.SetFlags(log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[scorecard-service] ")
	log.Println("Starting...")

	db = waitForDB(env("DB_DSN", "postgres://accio:accio_password@postgres:5432/accio?sslmode=disable"))
	nc = waitForNATS(env("NATS_URL", "nats://nats:4222"))

	// Subscribe to new catalog service events → auto-evaluate
	nc.Subscribe("idp.catalog.service.created", func(msg *nats.Msg) {
		var data map[string]string
		if err := json.Unmarshal(msg.Data, &data); err != nil {
			return
		}
		go evaluateService(data["id"], data["name"])
	})

	// Seed scorecards for existing services on startup
	go func() {
		time.Sleep(5 * time.Second) // let DB settle
		rows, err := db.Query(`
			SELECT cs.id, cs.name FROM catalog_services cs
			LEFT JOIN scorecards sc ON cs.id = sc.service_id
			WHERE sc.id IS NULL`)
		if err != nil {
			log.Printf("seed query failed: %v", err)
			return
		}
		defer rows.Close()
		for rows.Next() {
			var id, name string
			rows.Scan(&id, &name)
			evaluateService(id, name)
		}
	}()

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, 200, map[string]string{"status": "ok", "service": "scorecard-service"})
	})
	mux.HandleFunc("/scorecards", cors(scorecardsHandler))
	mux.HandleFunc("/scorecards/refresh", cors(refreshAllHandler))
	mux.HandleFunc("/scorecards/", cors(scorecardByServiceHandler))

	port := env("PORT", "8083")
	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
