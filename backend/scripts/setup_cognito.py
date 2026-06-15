"""One-time AWS Cognito setup for MediBot.

Creates:
  - a Cognito User Pool ("medibot-users")
  - an app client with USER_PASSWORD_AUTH enabled (no client secret)
  - five groups, one per role
  - five demo users, each assigned to their role group

Run:
    python scripts/setup_cognito.py
Then copy the printed pool id + client id into backend/.env.
"""
from __future__ import annotations

import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REGION = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION", "us-east-2")
POOL_NAME = "medibot-users"
DEMO_PASSWORD = os.environ.get("MEDIBOT_DEMO_PASSWORD", "MediBot@2026!")

DEMO_USERS = [
    ("dr.mehta", "doctor"),
    ("nurse.priya", "nurse"),
    ("billing.ravi", "billing_executive"),
    ("tech.anand", "technician"),
    ("admin.sys", "admin"),
]
ROLES = [r for _, r in DEMO_USERS]


def main() -> None:
    idp = boto3.client("cognito-idp", region_name=REGION)

    # --- user pool ---
    existing = idp.list_user_pools(MaxResults=60)["UserPools"]
    pool = next((p for p in existing if p["Name"] == POOL_NAME), None)
    if pool:
        pool_id = pool["Id"]
        print(f"User pool already exists: {pool_id}")
    else:
        pool_id = idp.create_user_pool(
            PoolName=POOL_NAME,
            Policies={"PasswordPolicy": {
                "MinimumLength": 8, "RequireUppercase": True,
                "RequireLowercase": True, "RequireNumbers": True,
                "RequireSymbols": True,
            }},
            AdminCreateUserConfig={"AllowAdminCreateUserOnly": True},
        )["UserPool"]["Id"]
        print(f"Created user pool: {pool_id}")

    # --- app client ---
    clients = idp.list_user_pool_clients(UserPoolId=pool_id, MaxResults=60)["UserPoolClients"]
    client = next((c for c in clients if c["ClientName"] == "medibot-backend"), None)
    if client:
        client_id = client["ClientId"]
        print(f"App client already exists: {client_id}")
    else:
        client_id = idp.create_user_pool_client(
            UserPoolId=pool_id,
            ClientName="medibot-backend",
            GenerateSecret=False,
            ExplicitAuthFlows=[
                "ALLOW_USER_PASSWORD_AUTH",
                "ALLOW_REFRESH_TOKEN_AUTH",
            ],
            AccessTokenValidity=8,
            TokenValidityUnits={"AccessToken": "hours"},
        )["UserPoolClient"]["ClientId"]
        print(f"Created app client: {client_id}")

    # --- groups (one per role) ---
    for role in ROLES:
        try:
            idp.create_group(UserPoolId=pool_id, GroupName=role,
                             Description=f"MediBot role: {role}")
            print(f"Created group: {role}")
        except idp.exceptions.GroupExistsException:
            print(f"Group exists: {role}")

    # --- demo users ---
    for username, role in DEMO_USERS:
        try:
            idp.admin_create_user(
                UserPoolId=pool_id,
                Username=username,
                MessageAction="SUPPRESS",
            )
            print(f"Created user: {username}")
        except idp.exceptions.UsernameExistsException:
            print(f"User exists: {username}")
        idp.admin_set_user_password(
            UserPoolId=pool_id, Username=username,
            Password=DEMO_PASSWORD, Permanent=True,
        )
        idp.admin_add_user_to_group(
            UserPoolId=pool_id, Username=username, GroupName=role
        )
        print(f"  -> password set, added to group '{role}'")

    print("\n=== Add to backend/.env ===")
    print(f"COGNITO_USER_POOL_ID={pool_id}")
    print(f"COGNITO_APP_CLIENT_ID={client_id}")
    print(f"COGNITO_REGION={REGION}")
    print(f"\nDemo password for all users: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
