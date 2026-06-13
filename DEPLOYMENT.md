# MediBot — AWS Deployment Guide

Target architecture: **EC2** (FastAPI backend in Docker) + **Amplify Hosting** (Next.js frontend) + **Cognito** (auth) + **S3** (documents) + **Bedrock** (LLM) + **Qdrant Cloud** (vectors).

```
GitHub repo ──> Amplify Hosting (HTTPS frontend)
                      │  NEXT_PUBLIC_API_URL
                      ▼
            EC2 (Docker: FastAPI :8000)
             │ IAM role (no keys on disk)
             ├── Cognito  (login / JWT verify)
             ├── S3       (document source)
             ├── Bedrock  (Claude inference)
             └── Qdrant Cloud (hybrid search)
```

---

## Phase 0 — Prerequisites (once)

1. **Bedrock model access**: AWS Console → Bedrock → *Model access* → request access to **Anthropic Claude** in your region (e.g. `ap-south-1`). Wait until status is "Access granted".
2. **Qdrant Cloud**: create a free cluster at https://cloud.qdrant.io → note the **URL** and **API key**.
3. **GitHub**: push the `medibot/` repo (public, per the assignment).

## Phase 1 — IAM role for EC2

Create role `medibot-ec2-role` (trusted entity: EC2) with this inline policy — the instance then needs **no AWS keys in `.env`** (boto3 uses the instance profile automatically):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": "*" },
    { "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket", "s3:PutObject", "s3:CreateBucket"],
      "Resource": ["arn:aws:s3:::mediassist-documents", "arn:aws:s3:::mediassist-documents/*"] },
    { "Effect": "Allow",
      "Action": ["cognito-idp:InitiateAuth", "cognito-idp:AdminCreateUser",
                  "cognito-idp:AdminSetUserPassword", "cognito-idp:AdminAddUserToGroup",
                  "cognito-idp:CreateUserPool", "cognito-idp:CreateUserPoolClient",
                  "cognito-idp:CreateGroup", "cognito-idp:ListUserPools",
                  "cognito-idp:ListUserPoolClients"],
      "Resource": "*" }
  ]
}
```

(After first-time setup you can trim the `cognito-idp:Create*/Admin*` actions down to just `InitiateAuth`.)

## Phase 2 — EC2 instance

1. **Launch**: Ubuntu 24.04, **t3.large** (8 GB RAM — Docling + the reranker need headroom), 30 GB gp3 disk, IAM role `medibot-ec2-role`.
2. **Security group**:
   - Inbound 22 (SSH) from *your IP only*
   - Inbound 8000 (HTTP API) from 0.0.0.0/0 (or 443 if you add Nginx+TLS, see Phase 6)
3. **Install Docker**:
   ```bash
   sudo apt update && sudo apt install -y docker.io git
   sudo usermod -aG docker ubuntu && newgrp docker
   ```
4. **Clone and configure**:
   ```bash
   git clone https://github.com/<you>/medibot.git && cd medibot/backend
   cp .env.example .env && nano .env
   ```
   Fill in `.env` — leave `AWS_ACCESS_KEY_ID`/`SECRET` **blank/deleted** (IAM role covers it). Set:
   - `QDRANT_URL`, `QDRANT_API_KEY`
   - `BEDROCK_MODEL_ID`, `AWS_REGION`
   - `S3_BUCKET`, `S3_PREFIX`
   - `FRONTEND_ORIGINS=http://localhost:3000` (you'll append the Amplify URL in Phase 5)

## Phase 3 — Cognito, data, ingestion (run on the EC2 box)

```bash
cd ~/medibot/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Cognito: pool + 5 role groups + 5 demo users
python scripts/setup_cognito.py
#    → paste the printed COGNITO_USER_POOL_ID / COGNITO_APP_CLIENT_ID into .env

# 2. Dataset: copy data/ (collections + mediassist.db) to the instance, e.g.
#    scp -r data ubuntu@<ec2-ip>:~/medibot/data
python scripts/upload_to_s3.py --data-dir ../data     # data/ → S3

# 3. Ingestion: S3 → Docling → Qdrant (first run downloads models, be patient)
python scripts/run_ingestion.py
```

## Phase 4 — Run the backend container

```bash
cd ~/medibot/backend
docker build -t medibot-api .
docker run -d --name medibot --restart unless-stopped \
  -p 8000:8000 \
  --env-file .env \
  -v ~/medibot/data:/srv/data \
  medibot-api

curl http://localhost:8000/health     # → {"status":"ok",...}
```

Test from your laptop: `curl http://<ec2-public-ip>:8000/health`.

## Phase 5 — Frontend on Amplify Hosting

1. AWS Console → **Amplify** → *Create new app* → connect your GitHub repo/branch.
2. Amplify detects Next.js; the repo's `frontend/amplify.yml` sets the monorepo build (app root: `frontend`).
3. Add environment variable: `NEXT_PUBLIC_API_URL = http://<ec2-public-ip>:8000` (or your HTTPS URL from Phase 6).
4. Deploy → note the app URL, e.g. `https://main.dxxxxxxxxx.amplifyapp.com`.
5. **Close the CORS loop** on EC2: edit `.env` →
   `FRONTEND_ORIGINS=https://main.dxxxxxxxxx.amplifyapp.com`
   then `docker restart medibot`.

> Amplify serves HTTPS; browsers block HTTPS pages calling a plain-HTTP API ("mixed content"). For the demo either do Phase 6 (recommended), or test the frontend locally (`npm run dev`) against the EC2 API.

## Phase 6 — HTTPS for the API (recommended)

Cheapest path — Caddy reverse proxy with automatic TLS:

```bash
# point a DNS name at the EC2 IP first (e.g. api.yourdomain.com, or use DuckDNS for free)
sudo apt install -y caddy
echo 'api.yourdomain.com {
    reverse_proxy localhost:8000
}' | sudo tee /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

Open inbound 443 in the security group, set `NEXT_PUBLIC_API_URL=https://api.yourdomain.com` in Amplify, and redeploy.

## Phase 7 — Verify the deployment

1. `GET https://<api>/health` → ok
2. Log in on the Amplify URL as each of the 5 demo users (password from `setup_cognito.py`, default `MediBot@2026!`)
3. Run the 3 adversarial prompts from `README.md` as `nurse` / `technician` / `billing_executive` → screenshot the refusals for the README
4. As `billing.ravi`, ask the 4 SQL RAG questions → confirm the `SQL RAG` label
5. As `admin.sys`, confirm all collections answer with citations

## Cost & teardown

Rough demo cost: t3.large ≈ $0.08/hr (~$2/day), Amplify free tier, Qdrant free tier, Cognito free tier, Bedrock pay-per-token (cents for a demo). **Teardown:** terminate the EC2 instance, delete the Amplify app, S3 bucket, Cognito user pool, and the Qdrant cluster.

## Production hardening (beyond the assignment)

Move `.env` secrets to SSM Parameter Store, put the API behind an ALB with ACM certs, pin the security group to Amplify/CloudFront ranges, turn on CloudWatch logs for the container (`--log-driver=awslogs`), and switch Cognito to SRP auth flow in the frontend instead of password passthrough.
