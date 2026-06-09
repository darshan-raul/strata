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

// ── Teams ────────────────────────────────────────────────────

type Team struct {
	ID           string    `json:"id"`
	Name         string    `json:"name"`
	Email        string    `json:"email"`
	SlackChannel string    `json:"slack_channel"`
	CreatedAt    time.Time `json:"created_at"`
}

func teamsHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		rows, err := db.Query(`SELECT id, name, COALESCE(email,''), COALESCE(slack_channel,''), created_at FROM catalog_teams ORDER BY name`)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		defer rows.Close()
		teams := []Team{}
		for rows.Next() {
			var t Team
			if err := rows.Scan(&t.ID, &t.Name, &t.Email, &t.SlackChannel, &t.CreatedAt); err != nil {
				log.Printf("scan error: %v", err)
				continue
			}
			teams = append(teams, t)
		}
		jsonResp(w, 200, teams)

	case http.MethodPost:
		var t Team
		if err := json.NewDecoder(r.Body).Decode(&t); err != nil {
			jsonResp(w, 400, map[string]string{"error": err.Error()})
			return
		}
		var id string
		err := db.QueryRow(`INSERT INTO catalog_teams (name,email,slack_channel) VALUES ($1,$2,$3) RETURNING id`,
			t.Name, t.Email, t.SlackChannel).Scan(&id)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		payload, _ := json.Marshal(map[string]string{"id": id, "name": t.Name})
		if err := nc.Publish("idp.catalog.team.created", payload); err != nil {
			log.Printf("publish error: %v", err)
		}
		jsonResp(w, 201, map[string]string{"id": id})
	}
}

// ── Catalog Services ─────────────────────────────────────────

type CatalogService struct {
	ID            string    `json:"id"`
	Name          string    `json:"name"`
	Description   string    `json:"description"`
	TeamID        string    `json:"team_id"`
	Language      string    `json:"language"`
	RepoURL       string    `json:"repo_url"`
	Lifecycle     string    `json:"lifecycle"`
	Type          string    `json:"type"`
	HasDocs       bool      `json:"has_docs"`
	HasSLO        bool      `json:"has_slo"`
	HasAPISpec    bool      `json:"has_api_spec"`
	HasMonitoring bool      `json:"has_monitoring"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

func catalogServicesHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		rows, err := db.Query(`
			SELECT id, name, COALESCE(description,''), COALESCE(team_id::text,''),
			       COALESCE(language,''), COALESCE(repo_url,''), lifecycle, type,
			       has_docs, has_slo, has_api_spec, has_monitoring, created_at, updated_at
			FROM catalog_services ORDER BY created_at DESC`)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		defer rows.Close()
		svcs := []CatalogService{}
		for rows.Next() {
			var s CatalogService
			if err := rows.Scan(&s.ID, &s.Name, &s.Description, &s.TeamID, &s.Language,
				&s.RepoURL, &s.Lifecycle, &s.Type, &s.HasDocs, &s.HasSLO, &s.HasAPISpec,
				&s.HasMonitoring, &s.CreatedAt, &s.UpdatedAt); err != nil {
				log.Printf("scan error: %v", err)
				continue
			}
			svcs = append(svcs, s)
		}
		jsonResp(w, 200, svcs)

	case http.MethodPost:
		var s CatalogService
		if err := json.NewDecoder(r.Body).Decode(&s); err != nil {
			jsonResp(w, 400, map[string]string{"error": err.Error()})
			return
		}
		if s.Lifecycle == "" {
			s.Lifecycle = "experimental"
		}
		if s.Type == "" {
			s.Type = "service"
		}
		teamID := sql.NullString{String: s.TeamID, Valid: s.TeamID != ""}
		var id string
		err := db.QueryRow(`
			INSERT INTO catalog_services
			  (name,description,team_id,language,repo_url,lifecycle,type,has_docs,has_slo,has_api_spec,has_monitoring)
			VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id`,
			s.Name, s.Description, teamID, s.Language, s.RepoURL, s.Lifecycle, s.Type,
			s.HasDocs, s.HasSLO, s.HasAPISpec, s.HasMonitoring).Scan(&id)
		if err != nil {
			jsonResp(w, 500, map[string]string{"error": err.Error()})
			return
		}
		payload, _ := json.Marshal(map[string]string{"id": id, "name": s.Name, "type": s.Type})
		if err := nc.Publish("idp.catalog.service.created", payload); err != nil {
			log.Printf("publish error: %v", err)
		}
		log.Printf("[catalog] service registered: %s (%s)", s.Name, id)
		jsonResp(w, 201, map[string]string{"id": id})
	}
}

func catalogServiceByIDHandler(w http.ResponseWriter, r *http.Request) {
	id := strings.TrimPrefix(r.URL.Path, "/catalog/services/")
	var s CatalogService
	err := db.QueryRow(`
		SELECT id, name, COALESCE(description,''), COALESCE(team_id::text,''),
		       COALESCE(language,''), COALESCE(repo_url,''), lifecycle, type,
		       has_docs, has_slo, has_api_spec, has_monitoring, created_at, updated_at
		FROM catalog_services WHERE id=$1`, id).Scan(
		&s.ID, &s.Name, &s.Description, &s.TeamID, &s.Language,
		&s.RepoURL, &s.Lifecycle, &s.Type, &s.HasDocs, &s.HasSLO, &s.HasAPISpec,
		&s.HasMonitoring, &s.CreatedAt, &s.UpdatedAt)
	if err == sql.ErrNoRows {
		jsonResp(w, 404, map[string]string{"error": "not found"})
		return
	}
	if err != nil {
		jsonResp(w, 500, map[string]string{"error": err.Error()})
		return
	}
	jsonResp(w, 200, s)
}

func statsHandler(w http.ResponseWriter, r *http.Request) {
	var total, production, experimental, beta int
	if err := db.QueryRow(`SELECT COUNT(*) FROM catalog_services`).Scan(&total); err != nil {
		log.Printf("count total error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM catalog_services WHERE lifecycle='production'`).Scan(&production); err != nil {
		log.Printf("count production error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM catalog_services WHERE lifecycle='experimental'`).Scan(&experimental); err != nil {
		log.Printf("count experimental error: %v", err)
	}
	if err := db.QueryRow(`SELECT COUNT(*) FROM catalog_services WHERE lifecycle='beta'`).Scan(&beta); err != nil {
		log.Printf("count beta error: %v", err)
	}
	var teamCount int
	if err := db.QueryRow(`SELECT COUNT(*) FROM catalog_teams`).Scan(&teamCount); err != nil {
		log.Printf("count teams error: %v", err)
	}
	jsonResp(w, 200, map[string]int{
		"total_services":   total,
		"production":       production,
		"experimental":     experimental,
		"beta":             beta,
		"teams":            teamCount,
	})
}

func main() {
	log.SetFlags(log.Ltime | log.Lmsgprefix)
	log.SetPrefix("[catalog-service] ")
	log.Println("Starting...")

	db = waitForDB(env("DB_DSN", "postgres://strata:strata_password@postgres:5432/strata?sslmode=disable"))
	nc = waitForNATS(env("NATS_URL", "nats://nats:4222"))

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		jsonResp(w, 200, map[string]string{"status": "ok", "service": "catalog-service"})
	})
	mux.HandleFunc("/catalog/services", cors(catalogServicesHandler))
	mux.HandleFunc("/catalog/services/", cors(catalogServiceByIDHandler))
	mux.HandleFunc("/catalog/teams", cors(teamsHandler))
	mux.HandleFunc("/catalog/stats", cors(statsHandler))

	port := env("PORT", "8081")
	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
