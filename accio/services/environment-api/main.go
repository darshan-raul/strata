package main

import (
	"fmt"
	"net/http"
)

func main() {
	fmt.Printf("Starting environment-api...\n")
	http.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})
	http.ListenAndServe(":8082", nil)
}
