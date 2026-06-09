import json
import os
import uuid
import boto3
from datetime import datetime, timezone, timedelta
from decimal import Decimal

sfn = boto3.client("stepfunctions")
ddb = boto3.resource("dynamodb")

# Environment Variables
SFN_CREATE_ARN = os.environ.get("SFN_CREATE_ARN")
CLUSTERS_TABLE = os.environ.get("CLUSTERS_TABLE")
EXTERNAL_ID = os.environ.get("EXTERNAL_ID", "strata-provisioner-v1")

# Helper to convert Decimal for json serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method")
        path = event.get("rawPath", "")
        
        # Get JWT claims
        authorizer = event.get("requestContext", {}).get("authorizer", {})
        jwt = authorizer.get("jwt", {})
        claims = jwt.get("claims", {})
        
        user_id = claims.get("sub")
        
        if not user_id:
            return _response(401, {"message": "Unauthorized: No user_id found in JWT"})
            
        table = ddb.Table(CLUSTERS_TABLE)

        if method == "POST" and path == "/clusters":
            body = json.loads(event.get("body", "{}"))
            
            # fallback to body for aws_account_id if not in claims
            aws_account_id = claims.get("custom:aws_account_id")
            if not aws_account_id:
               aws_account_id = body.get("aws_account_id")
               
            if not aws_account_id:
                 return _response(400, {"message": "Missing aws_account_id"})
                 
            provider = body.get("provider", "aws")
            region = body.get("region", "ap-south-1")
            instance_type = body.get("instance_type", "t3.medium")
            # Generate cluster ID
            cluster_id = f"eks-{user_id[:8]}-{uuid.uuid4().hex[:6]}"
            name = body.get("name", cluster_id)
            
            now = datetime.now(timezone.utc).isoformat()
            expires = int((datetime.now(timezone.utc) + timedelta(hours=4)).timestamp())

            item = {
                "user_id": user_id,
                "cluster_id": cluster_id,
                "name": name,
                "status": "INITIATED",
                "current_step": "STARTED",
                "provider": provider,
                "region": region,
                "instance_type": instance_type,
                "aws_account_id": aws_account_id,
                "github_repo": body.get("github_repo", ""),
                "created_at": now,
                "updated_at": now,
                "expires_at": expires,
            }
            
            table.put_item(Item=item)
            
            # Start step functions
            sfn_input = {
                "user_id": user_id,
                "cluster_id": cluster_id,
                "aws_account_id": aws_account_id,
                "provider": provider,
                "region": region,
                "instance_type": instance_type,
                "name": name,
                "external_id": EXTERNAL_ID
            }
            
            sfn.start_execution(
                stateMachineArn=SFN_CREATE_ARN,
                name=f"provision-{cluster_id}",
                input=json.dumps(sfn_input)
            )

            return _response(202, {"cluster_id": cluster_id, "status": "INITIATED"})

        elif method == "GET" and path.startswith("/clusters/"):
            # Extract cluster_id from path
            path_parts = path.strip("/").split("/")
            if len(path_parts) != 2:
                 return _response(400, {"message": "Invalid path for GET cluster"})
            cluster_id = path_parts[1]
            
            response = table.get_item(Key={"user_id": user_id, "cluster_id": cluster_id})
            item = response.get("Item")
            
            if not item:
                return _response(404, {"message": f"Cluster {cluster_id} not found"})
                
            return _response(200, item)

        return _response(405, {"message": f"Method {method} not allowed on {path}"})
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return _response(500, {"message": "Internal server error"})


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, cls=DecimalEncoder)
    }
