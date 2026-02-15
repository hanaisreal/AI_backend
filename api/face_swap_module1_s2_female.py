import os
import json
import time
import asyncio
from typing import Optional

import httpx
from dotenv import load_dotenv


# ==========================================
# Configure here
# ==========================================

# 1) Put the user image URL here before running
USER_IMAGE_URL = "https://deepfake-videomaking.s3.us-east-1.amazonaws.com/user_uploads/user_AI.jpeg"  # <-- fill this with the user's image URL

# 2) Base image for Module 1, Scenario 2 (female)
BASE_IMAGE_URL = "https://d3srmxrzq4dz1v.cloudfront.net/video-url/fakenews-case2-female.png"


# ==========================================
# Akool auth
# ==========================================

load_dotenv()
AKOOL_CLIENT_ID = os.getenv("AKOOL_CLIENT_ID")
AKOOL_CLIENT_SECRET = os.getenv("AKOOL_CLIENT_SECRET")
AKOOL_API_KEY = os.getenv("AKOOL_API_KEY")  # optional direct key

_akool_token: Optional[str] = None
_akool_token_expiry: float = 0


async def get_akool_token() -> str:
    global _akool_token, _akool_token_expiry
    now = time.time()
    if _akool_token and now < _akool_token_expiry:
        return _akool_token

    if AKOOL_API_KEY and not AKOOL_CLIENT_ID:
        # direct key flow
        return AKOOL_API_KEY

    if not AKOOL_CLIENT_ID or not AKOOL_CLIENT_SECRET:
        raise RuntimeError("Akool credentials missing. Set AKOOL_CLIENT_ID and AKOOL_CLIENT_SECRET or AKOOL_API_KEY.")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://openapi.akool.com/api/open/v3/getToken",
            headers={"Content-Type": "application/json"},
            json={"clientId": AKOOL_CLIENT_ID, "clientSecret": AKOOL_CLIENT_SECRET},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 1000:
            raise RuntimeError(f"Akool token error: {data.get('msg', 'Unknown error')}")
        _akool_token = data.get("token")
        _akool_token_expiry = now + 3600 * 24 * 365  # 1 year
        return _akool_token


# ==========================================
# Face swap util
# ==========================================

def load_base_image_opts(config_path: str, base_image_url: str) -> str:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for _, img_cfg in cfg.get("base_images", {}).items():
        if img_cfg.get("url") == base_image_url:
            opts = img_cfg.get("opts")
            if not opts:
                raise RuntimeError("Face opts not configured for base image. Run detect and update config.")
            return opts
    raise RuntimeError("Base image not found in face_swap_config.json")


async def detect_face_opts(image_url: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://sg3.akool.com/detect",
            headers={"Content-Type": "application/json"},
            json={"image_url": image_url},
        )
        resp.raise_for_status()
        data = resp.json()
        landmarks = data.get("landmarks_str", "")
        if not landmarks:
            raise RuntimeError("No face detected in user image")
        return landmarks


async def face_swap(user_image_url: str, base_image_url: str) -> str:
    if not user_image_url:
        raise ValueError("USER_IMAGE_URL is empty. Please set it at the top of this file.")

    token = await get_akool_token()

    # Load base image opts from local config
    config_path = os.path.join(os.path.dirname(__file__), "face_swap_config.json")
    base_opts = load_base_image_opts(config_path, base_image_url)

    # Detect user face opts
    user_opts = await detect_face_opts(user_image_url)

    payload = {
        "targetImage": [{"path": base_image_url, "opts": base_opts}],  # base
        "sourceImage": [{"path": user_image_url, "opts": user_opts}],  # user
        "face_enhance": 1,
        "modifyImage": base_image_url,
    }

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://openapi.akool.com/api/open/v3/faceswap/highquality/specifyimage",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 1000:
            raise RuntimeError(f"Akool error: {data.get('msg', 'Unknown error')}")

        result = data.get("data", {})
        result_url = result.get("url")
        task_id = result.get("_id") or result.get("job_id")

        if result_url:
            return result_url

        if not task_id:
            raise RuntimeError("Akool returned no url or task id")

        # Simple polling (every 10s, up to 2 minutes)
        status_url = (
            "https://openapi.akool.com/api/open/v3/faceswap/highquality/specifyimage/status?task_id="
            + task_id
        )
        for _ in range(12):
            await asyncio.sleep(10)
            status_resp = await client.get(status_url, headers={"Authorization": f"Bearer {token}"})
            status_resp.raise_for_status()
            status_data = status_resp.json()
            if status_data.get("code") == 1000:
                job = status_data.get("data", {})
                if job.get("status") == "completed":
                    url = job.get("url") or job.get("result_url")
                    if url:
                        return url
                elif job.get("status") == "failed":
                    raise RuntimeError("Face swap failed")

        raise RuntimeError("Face swap timed out while polling")


async def main() -> None:
    try:
        url = await face_swap(USER_IMAGE_URL, BASE_IMAGE_URL)
        print("✅ Face swap completed:", url)
    except Exception as e:
        print("❌ Face swap error:", e)


if __name__ == "__main__":
    asyncio.run(main())


