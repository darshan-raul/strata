I want to build a platform which will be used by developers/companies with existing codebases on github to create a production grade architecture based on cloudnative principles in their aws account along with gitops, observaiblity toolings. They are complete handsfree apart from granting access
to the github repos and aws account [to be later implemented on gcp and azure as well]. There will be a continous AI agent which in the first phase will analyze their codebase and add the missing parts to the code, create the dockerfiles and also the kubernetes manifests. And all through the existance of the architecture the ai agent will be continuously involved in watching the cluster and helping the user with a natural language interface to get more insights about the running applications and architecture and also to help them debug issues, redeploy and perform routine maintenance and etc. [The user should never have to touch the terminal for anything]. 

So this is a SaaS platform and currently we are starting with it being able to provision in aws. It will be flutter based because i want a web frontend for onboarding [most of the github and aws access grant workflows can only work through the web] and then a mobile frontend [android now, ios later] to monitor it.

The apps name is Strata [potterverse magic spell to summon things]. The flutter web frontend will be hosted on vercel/cloudflare pages and the mobile app I will start with just installing on my android. The backend will be completely serverless on AWS. Also the sample app to be used in demo will be a k8s mirror of the serverless backend, ill explain it in its section

Prerequisites:

- User should have 2 repos [code repo, ops repo] in github
- They should have a AWS account with root access to create roles

# Frontend

- This will be a Flutter app.
- The web frontend will be hosted on Vercel.
- The onboarding workflow will be as follows:
  - AWS Cognito will be the first point of entry to authenticate the user.
  - The user will grant the application access to their GitHub.
  - The user will provide their AWS Account ID, which is sent to the backend.
  - The backend generates a CloudFormation template and returns a backlink.
  - The user clicks the backlink, which redirects them to their AWS console to provision an IAM role using the template.
  - The application backend will later assume this IAM role to create and manage the architecture.

# AWS backend  

- The backend will be completely serverless.
- It will use API Gateway to receive all incoming requests.
- A Lambda orchestrator will handle communication with AWS Step Functions.
- Step Functions will act as the main orchestrator. Its responsibilities include:
  - Running Terraform on the client's AWS environment to provision infrastructure.
  - Monitoring whether the provisioned cluster is healthy or not (utilizing multiple Lambdas for this purpose).
  - Interacting with the Bedrock AI agent for continuous monitoring and anomaly detection.
- Data will be stored in DynamoDB.

# The sample target app and its infra

