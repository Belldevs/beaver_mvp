"""Tiny Supabase helper: PostgREST (tables), Storage, and token checking.
Uses the SERVICE ROLE key, so it must only ever run on the backend."""
import logging
import os

import httpx

log = logging.getLogger("beaver.db")
_client = httpx.Client(timeout=60)


class SupabaseError(Exception):
    pass


def _cfg():
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise SupabaseError("The backend is missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in backend/.env.")
    return url, key


def _headers(key, extra=None):
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    h.update(extra or {})
    return h


def _check(r: httpx.Response, what: str):
    if r.status_code >= 300:
        log.error("%s failed: %s %s", what, r.status_code, r.text[:500])
        raise SupabaseError(f"{what} failed ({r.status_code}).")


def get_user_id(token: str):
    """Ask Supabase Auth who this access token belongs to. Returns the user id or None."""
    url, key = _cfg()
    r = _client.get(f"{url}/auth/v1/user", headers={"apikey": key, "Authorization": f"Bearer {token}"})
    return r.json().get("id") if r.status_code == 200 else None


def select(table: str, params: dict) -> list[dict]:
    url, key = _cfg()
    r = _client.get(f"{url}/rest/v1/{table}", params=params, headers=_headers(key))
    _check(r, f"Reading {table}")
    return r.json()


def insert(table: str, row: dict) -> dict:
    url, key = _cfg()
    r = _client.post(f"{url}/rest/v1/{table}", json=row,
                     headers=_headers(key, {"Prefer": "return=representation"}))
    _check(r, f"Saving to {table}")
    return r.json()[0]


def delete(table: str, params: dict) -> None:
    url, key = _cfg()
    r = _client.delete(f"{url}/rest/v1/{table}", params=params, headers=_headers(key))
    _check(r, f"Deleting from {table}")


def storage_upload(bucket: str, path: str, data: bytes, content_type="application/octet-stream") -> None:
    url, key = _cfg()
    r = _client.post(f"{url}/storage/v1/object/{bucket}/{path}", content=data,
                     headers=_headers(key, {"Content-Type": content_type, "x-upsert": "true"}))
    _check(r, "Uploading to storage")


def storage_delete(bucket: str, paths: list[str]) -> None:
    if not paths:
        return
    url, key = _cfg()
    r = _client.request("DELETE", f"{url}/storage/v1/object/{bucket}", json={"prefixes": paths},
                        headers=_headers(key))
    _check(r, "Deleting from storage")


def update(table: str, params: dict, row: dict) -> None:
    url, key = _cfg()
    r = _client.patch(f"{url}/rest/v1/{table}", params=params, json=row, headers=_headers(key))
    _check(r, f"Updating {table}")


def storage_download(bucket: str, path: str) -> bytes:
    url, key = _cfg()
    r = _client.get(f"{url}/storage/v1/object/{bucket}/{path}", headers=_headers(key))
    _check(r, "Reading your sheet")
    return r.content
