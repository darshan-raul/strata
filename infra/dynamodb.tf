# ---------------------------------------------------------------------------
# clusters table
# ---------------------------------------------------------------------------

resource "aws_dynamodb_table" "clusters" {
  name         = "clusters"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "cluster_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "cluster_id"
    type = "S"
  }

  # TTL — items expire 4 hours after creation (set by orchestrator Lambda)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "Strata-clusters"
  }
}

# ---------------------------------------------------------------------------
# SSM — table name for Lambdas
# ---------------------------------------------------------------------------

resource "aws_ssm_parameter" "dynamodb_table_name" {
  name  = "/Strata/dynamodb/clusters-table"
  type  = "String"
  value = aws_dynamodb_table.clusters.name
}


