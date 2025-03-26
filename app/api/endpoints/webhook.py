from fastapi import APIRouter, Request, HTTPException, Header, status
from app.config import settings
from app.utils import git_api
from app.utils.client import silicon_client
from app.utils import euler_maker_api as maker
import hmac
import hashlib
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC signature of webhook payload."""
    try:
        digest = hmac.new(
            settings.webhook_secret.encode(),
            msg=body,
            digestmod=hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={digest}", signature)
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        return False


def extract_pr_data(data: dict) -> dict:
    """Extract and validate required PR data from webhook payload."""
    if data.get("noteable_type", "") != "PullRequest":
        raise ValueError("Not a pull request event")

    note = data.get("note", "").strip().lower()
    if note not in [cmd.strip().lower() for cmd in settings.accept_cmds]:
        raise ValueError("Unsupported command")

    pull_request = data.get("pull_request", {})
    project = data.get("project", {})

    return {
        "repo_url": project.get("url", ""),
        "source_url": pull_request.get("head", {}).get("repo", {}).get("url", ""),
        "pr_number": pull_request.get("number", ""),
        "repo_name": project.get("name", ""),
    }


@router.post("/webhooks/spec", status_code=status.HTTP_202_ACCEPTED)
async def handle_webhook(
        request: Request,
        x_signature: str = Header(..., alias="X-Signature")
):
    logger.info("Received webhook request")

    # Verify signature
    body = await request.body()
    if not verify_signature(body, x_signature):
        logger.warning("Invalid signature")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid signature")

    try:
        data = await request.json()
        pr_data = extract_pr_data(data)
    except ValueError as e:
        logger.info(f"Ignoring unsupported event: {e}")
        return
    except Exception as e:
        logger.error(f"Payload processing failed: {e}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid payload")

    try:
        # Fetch spec file
        spec_content = git_api.get_spec_content(
            pr_data["repo_url"],
            pr_data["pr_number"],
            f'{pr_data["repo_name"]}.spec'
        )

        # Get build log
        os_project = settings.os_project.format(
            repo=pr_data["repo_name"],
            pr_number=pr_data["pr_number"]
        )
        job_id = maker.get_job_id(os_project, pr_data["repo_name"])
        log_url = maker.get_log_url(maker.get_result_root(job_id))
        log_content = maker.get_build_log(log_url)

        # Analyze build log
        chat = silicon_client.SiliconFlowChat(settings.silicon_token)
        fixed_spec = chat.analyze_build_log(spec_content, log_content)

        # Update spec in fork
        fork_url, commit_sha = git_api.update_spec_file(
            pr_data["source_url"],
            fixed_spec,
            pr_data["pr_number"]
        )

        # Trigger Euler Maker build
        maker.add_software_package(
            settings.os_repair_project,
            pr_data["repo_name"],
            "",
            fork_url
        )
        maker.add_build_target(
            settings.os_repair_project,
            pr_data["repo_name"],
            settings.os_variant,
            settings.os_arch,
            settings.ground_projects,
            settings.flag_build,
            settings.flag_publish
        )
        maker.start_build_single(settings.os_repair_project, pr_data["repo_name"])

        # Post build status to PR
        comment = settings.fix_result_comment.format(
            commit_url=f"{fork_url}/commit/{commit_sha}",
            maker_url=(
                f"https://eulermaker.compass-ci.openeuler.openatom.cn/package/"
                f"overview?osProject={settings.os_repair_project}&packageName={pr_data['repo_name']}"
            )
        )
        git_api.comment_on_pr(
            pr_data["repo_url"],
            pr_data["pr_number"],
            comment
        )

        logger.info("Webhook processed successfully")
        return {"status": "processing_started"}
    except Exception as e:
        logger.critical(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(500, "Internal server error")