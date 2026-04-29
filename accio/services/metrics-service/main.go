package main

import (
	"fmt"
	"net/http"
)

func main() {
	fmt.Printf("Starting metrics-service...\n")
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})
	http.ListenAndServe(":8083", nil)
}
