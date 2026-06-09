resource "aws_sfn_state_machine" "provision_cluster" {
  name     = "strata-provision-cluster"
  role_arn = aws_iam_role.strata_sfn.arn
  type     = "STANDARD"

  definition = jsonencode({
    "Comment" : "Strata cluster provisioning — MVP step functions",
    "StartAt" : "UpdateStatusProvisioning",
    "States" : {
      "UpdateStatusProvisioning" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::dynamodb:updateItem",
        "Parameters" : {
          "TableName" : aws_dynamodb_table.clusters.name,
          "Key" : {
            "user_id" : { "S.$" : "$.user_id" },
            "cluster_id" : { "S.$" : "$.cluster_id" }
          },
          "UpdateExpression" : "SET #s=:s, current_step=:cs",
          "ExpressionAttributeNames" : { "#s" : "status" },
          "ExpressionAttributeValues" : {
            ":s" : { "S" : "PROVISIONING" },
            ":cs" : { "S" : "TERRAFORM_APPLY" }
          }
        },
        "ResultPath" : null,
        "Next" : "RunTerraform"
      },
      "RunTerraform" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::lambda:invoke.waitForTaskToken",
        "Parameters" : {
          "FunctionName" : aws_lambda_function.start_codebuild.arn,
          "Payload" : {
            "task_token.$" : "$$.Task.Token",
            "action" : "apply",
            "cluster_id.$" : "$.cluster_id",
            "user_id.$"    : "$.user_id",
            "provider.$"   : "$.provider",
            "aws_account_id.$" : "$.aws_account_id",
            "region.$" : "$.region",
            "instance_type.$" : "$.instance_type",
            "name.$" : "$.name"
          }
        },
        "HeartbeatSeconds" : 1800,
        "TimeoutSeconds" : 1800,
        "ResultPath" : "$.terraform_output",
        "Catch" : [
          {
            "ErrorEquals" : ["States.ALL"],
            "Next" : "HandleFailure",
            "ResultPath" : "$.error"
          }
        ],
        "Next" : "UpdateStatusReady"
      },
      "UpdateStatusReady" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::dynamodb:updateItem",
        "Parameters" : {
          "TableName" : aws_dynamodb_table.clusters.name,
          "Key" : {
            "user_id" : { "S.$" : "$.user_id" },
            "cluster_id" : { "S.$" : "$.cluster_id" }
          },
          "UpdateExpression" : "SET #s=:s, current_step=:cs, cluster_endpoint=:ep",
          "ExpressionAttributeNames" : { "#s" : "status" },
          "ExpressionAttributeValues" : {
            ":s" : { "S" : "READY" },
            ":cs" : { "S" : "COMPLETE" },
            ":ep" : { "S.$" : "$.terraform_output.cluster_endpoint" }
          }
        },
        "ResultPath" : null,
        "End" : true
      },
      "HandleFailure" : {
        "Type" : "Task",
        "Resource" : "arn:aws:states:::dynamodb:updateItem",
        "Parameters" : {
          "TableName" : aws_dynamodb_table.clusters.name,
          "Key" : {
            "user_id" : { "S.$" : "$.user_id" },
            "cluster_id" : { "S.$" : "$.cluster_id" }
          },
          "UpdateExpression" : "SET #s=:s, current_step=:cs, error_message=:err",
          "ExpressionAttributeNames" : { "#s" : "status" },
          "ExpressionAttributeValues" : {
            ":s" : { "S" : "FAILED" },
            ":cs" : { "S" : "FAILED" },
            ":err" : { "S.$" : "$.error.Cause" }
          }
        },
        "End" : true
      }
    }
  })
}

output "sfn_provision_cluster_arn" {
  value = aws_sfn_state_machine.provision_cluster.arn
}
