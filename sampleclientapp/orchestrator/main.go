package main

import (
	"context"
	"log"
	"os"
	"strconv"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/nats-io/nats.go"
)

var (
	db   *pgxpool.Pool
	nc   *nats.Conn
)

func initConnections() {
	var err error
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://user:password@postgres:5432/sampleapp?sslmode=disable"
	}
	db, err = pgxpool.New(context.Background(), dbURL)
	if err != nil {
		log.Fatalf("Unable to connect to database: %v\n", err)
	}

	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://nats:4222"
	}
	nc, err = nats.Connect(natsURL)
	if err != nil {
		log.Fatalf("Unable to connect to NATS: %v\n", err)
	}
}

func main() {
	initConnections()
	defer db.Close()
	defer nc.Close()

	app := fiber.New()
	app.Use(logger.New())

	app.Post("/api/jobs", createJob)
	app.Get("/api/jobs", getJobs)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Fatal(app.Listen(":" + port))
}

type CreateJobRequest struct {
	Name string `json:"name"`
}

func createJob(c *fiber.Ctx) error {
	var req CreateJobRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	var id int
	err := db.QueryRow(context.Background(), "INSERT INTO jobs (name, status) VALUES ($1, 'PENDING') RETURNING id", req.Name).Scan(&id)
	if err != nil {
		log.Printf("DB error: %v", err)
		return c.Status(500).JSON(fiber.Map{"error": "Failed to create job"})
	}

	// Publish to NATS
	err = nc.Publish("job.created", []byte(strconv.Itoa(id)))
	if err != nil {
		log.Printf("NATS error: %v", err)
	}

	return c.Status(201).JSON(fiber.Map{"id": id, "status": "PENDING"})
}

func getJobs(c *fiber.Ctx) error {
	rows, err := db.Query(context.Background(), "SELECT id, name, status, created_at, updated_at FROM jobs ORDER BY created_at DESC LIMIT 50")
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "Failed to fetch jobs"})
	}
	defer rows.Close()

	type Job struct {
		ID        int    `json:"id"`
		Name      string `json:"name"`
		Status    string `json:"status"`
		CreatedAt string `json:"created_at"`
		UpdatedAt string `json:"updated_at"`
	}

	var jobs []Job
	for rows.Next() {
		var j Job
		var ca, ua interface{} // ignoring actual time mapping for simplicity in this sample
		if err := rows.Scan(&j.ID, &j.Name, &j.Status, &ca, &ua); err == nil {
			jobs = append(jobs, j)
		}
	}
	return c.JSON(jobs)
}
