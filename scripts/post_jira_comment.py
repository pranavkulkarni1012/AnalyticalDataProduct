#!/usr/bin/env python3
"""Post a deployment validation comment to a Jira ticket.

Used by Harness CD pipeline to report deployment status at each environment.

Usage:
    python scripts/post_jira_comment.py \
        --ticket SCRUM-42 \
        --environment dev \
        --status SUCCESS \
        --artifact-version 123 \
        --summary "DEV deployment passed"

Exit codes:
    0 - Comment posted successfully
    1 - Error occurred
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import uuid as _uuid

_CORRELATION_ID = str(_uuid.uuid4())

logging.basicConfig(
    format='{"time":"%(asctime)s","level":"%(levelname)s","correlation_id":"' + _CORRELATION_ID + '","msg":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_comment(environment, status, artifact_version, summary):
    """Build a structured Jira comment."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_emoji = "PASS" if "SUCCESS" in status.upper() else "FAIL"

    comment = (
        f"**Deployment Validation Report**\n\n"
        f"| Field | Value |\n"
        f"|-------|-------|\n"
        f"| Environment | {environment.upper()} |\n"
        f"| Status | {status_emoji} {status} |\n"
        f"| Artifact Version | {artifact_version} |\n"
        f"| Timestamp | {timestamp} |\n\n"
        f"**Summary:** {summary}"
    )
    return comment


def post_comment_api(ticket, comment, jira_url, jira_token):
    """Post comment to Jira via Secrets Manager-sourced credentials.

    Retrieves JIRA API credentials from AWS Secrets Manager rather than
    environment variables, per CLAUDE.md hard constraints.
    Note: In the full AI SDLC pipeline, Jira comments are posted via the
    Atlassian MCP tools (mcp__atlassian__addCommentToJiraIssue). This script
    exists as a fallback for CI/CD environments (Harness) where MCP is not
    available. It retrieves credentials from Secrets Manager (not env vars).
    """
    import urllib.request
    import urllib.error

    try:
        secrets_client = boto3.client("secretsmanager")
        secret_value = secrets_client.get_secret_value(SecretId="adp/jira/api-token")
        secret = json.loads(secret_value["SecretString"])
        api_token = secret["api_token"]
        api_email = secret["email"]
    except Exception as e:
        logger.error("Failed to retrieve Jira credentials from Secrets Manager: %s", e)
        return False

    url = f"{jira_url}/rest/api/3/issue/{ticket}/comment"

    import base64
    auth_str = base64.b64encode(f"{api_email}:{api_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/json",
    }
    body = json.dumps({
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment}],
                }
            ],
        }
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                logger.info("Comment posted to %s", ticket)
                return True
    except urllib.error.HTTPError as e:
        logger.error("Failed to post comment: HTTP %d - %s", e.code, e.reason)
        return False
    except urllib.error.URLError as e:
        logger.error("Failed to connect to Jira: %s", e.reason)
        return False

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Post deployment validation report to Jira"
    )
    parser.add_argument("--ticket", required=True, help="Jira ticket key (e.g., SCRUM-42)")
    parser.add_argument(
        "--environment",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Deployment environment",
    )
    parser.add_argument("--status", required=True, help="Deployment status (e.g., SUCCESS, FAILED)")
    parser.add_argument("--artifact-version", required=True, help="Build/artifact version")
    parser.add_argument("--summary", required=True, help="Validation summary message")
    parser.add_argument("--dry-run", action="store_true", help="Print comment without posting")
    args = parser.parse_args()

    comment = build_comment(args.environment, args.status, args.artifact_version, args.summary)

    if args.dry_run:
        print(comment)
        sys.exit(0)

    jira_url = os.environ.get("JIRA_URL")

    if not jira_url:
        logger.error("JIRA_URL environment variable is required")
        sys.exit(1)

    success = post_comment_api(args.ticket, comment, jira_url, None)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
